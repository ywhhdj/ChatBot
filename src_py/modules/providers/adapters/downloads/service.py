"""统一下载执行器：从 ProviderSpec.download 生成 plan 并执行。"""
from __future__ import annotations

import asyncio
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ....logger import logger
from ....utils.http import download_file
from .models import DownloadPlan,DownloadItem

class ModelDownload:
    async def plan(self, spec) -> DownloadPlan:
        """把 spec.download 解析成可执行 plan。"""
        d = spec.download
        if not d:
            raise ValueError(f"{spec.provider_id} 未声明 download 配置")
        strategy = str(d.get("strategy") or "http-file")
        if strategy == "manual":
            raise ValueError(f"{spec.provider_id} 需要手动下载，不支持自动执行")

        target_dir = self._resolve_target_dir(spec, d)
        files = d.get("files") or {}
        if not isinstance(files, dict) or not files:
            raise ValueError("download.files 必须是非空对象")

        # 模板变量替换：{model_size} 从选中模型的 params 取
        model_params = {}
        for m in spec.models:
            if m.get("id") == spec.model_id:
                model_params = m.get("params") or {}
                break
        resolved = {k: self._render(v, model_params) for k, v in files.items()}

        archive = str(d.get("archive") or "").lower() or None
        items: List[DownloadItem] = []
        for name, url in resolved.items():
            if strategy == "huggingface":
                target = target_dir  # repo 拉到目录
            elif archive:
                target = target_dir / name
            else:
                target = target_dir / name
            items.append(DownloadItem(
                name=name,
                url=url,
                target=target,
                archive=archive
            ))

        return DownloadPlan(
            capability=spec.capability,
            provider=spec.provider_id,
            strategy=strategy,
            target_dir=target_dir,
            items=items,
            meta={k: d.get(k) for k in ("license", "source", "docs_url", "size_mb")},
        )

    async def execute(
        self,
        plan: DownloadPlan,
        progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        if plan.strategy == "huggingface":
            return await self._run_hf(plan, progress_callback)
        return await self._run_http(plan, progress_callback)

    # ---------- HTTP ----------

    async def _run_http(self, plan: DownloadPlan, cb) -> Dict[str, Any]:
        plan.target_dir.mkdir(parents=True, exist_ok=True)
        total = len(plan.items)
        done = {"n": 0}
        results = []

        async def run_one(item: DownloadItem) -> Dict[str, Any]:
            async def on_progress(pct: int):
                overall = int((done["n"] * 100 + pct) / total)
                await self._emit(cb, {
                    "phase": "download",
                    "provider": plan.provider,
                    "file": item.name,
                    "progress": overall,
                })

            item.target.parent.mkdir(parents=True, exist_ok=True)
            tmp = item.target.with_suffix(item.target.suffix + ".part")
            try:
                if item.archive == "tar":
                    archive_path = tmp.with_suffix(tmp.suffix + ".tar")
                    await download_file(item.url, archive_path, progress_callback=on_progress)
                    await self._extract(archive_path, item.target, "tar")
                    archive_path.unlink(missing_ok=True)
                elif item.archive == "zip":
                    archive_path = tmp.with_suffix(tmp.suffix + ".zip")
                    await download_file(item.url, archive_path, progress_callback=on_progress)
                    await self._extract(archive_path, item.target, "zip")
                    archive_path.unlink(missing_ok=True)
                else:
                    await download_file(item.url, tmp, progress_callback=on_progress)
                    tmp.replace(item.target)
                done["n"] += 1
                await self._emit(cb, {
                    "phase": "download",
                    "provider": plan.provider,
                    "file": item.name,
                    "progress": int(done["n"] * 100 / total),
                    "done": True,
                })
                return {"name": item.name, "success": True, "path": str(item.target)}
            except Exception as exc:  # noqa: BLE001
                tmp.unlink(missing_ok=True)
                logger.error(f"[Download] {plan.provider}/{item.name} 失败: {exc}")
                return {"name": item.name, "success": False, "error": str(exc)}

        for r in await asyncio.gather(*[run_one(i) for i in plan.items]):
            results.append(r)

        await self._emit(cb, {"phase": "complete", "provider": plan.provider, "progress": 100})
        return {
            "success": all(r["success"] for r in results),
            "provider": plan.provider,
            "target_dir": str(plan.target_dir),
            "items": results,
        }

    # ---------- HuggingFace ----------

    async def _run_hf(self, plan: DownloadPlan, cb) -> Dict[str, Any]:
        repo = plan.items[0].url if plan.items else ""
        if not repo:
            return {"success": False, "error": "huggingface 下载缺少 repo"}
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            return {
                "success": False,
                "error": "未安装 huggingface_hub"
            }

        await self._emit(cb, {
            "phase": "download",
            "provider": plan.provider,
            "progress": 5
        })
        loop = asyncio.get_event_loop()

        def _do():
            plan.target_dir.mkdir(parents=True, exist_ok=True)
            return snapshot_download(repo_id=repo, local_dir=str(plan.target_dir))

        try:
            path = await loop.run_in_executor(None, _do)
            await self._emit(cb, {"phase": "complete", "provider": plan.provider, "progress": 100})
            return {"success": True, "provider": plan.provider, "target_dir": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    # ---------- helpers ----------

    async def _extract(self, archive: Path, target: Path, kind: str) -> None:
        def _do():
            target.mkdir(parents=True, exist_ok=True)
            if kind == "tar":
                with tarfile.open(archive) as tar:
                    tar.extractall(target)
            elif kind == "zip":
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(target)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _do)

    @staticmethod
    def _resolve_target_dir(spec, d) -> Path:
        raw = d.get("target_dir") or spec.endpoint.get("model_dir") or ""
        if "${" in str(raw):
            raise ValueError(f"target_dir 含未解析环境变量: {raw}")
        if not raw:
            raise ValueError("download.target_dir 与 endpoint.model_dir 均为空")
        return Path(raw)

    @staticmethod
    def _render(template: Any, params: Dict[str, Any]) -> str:
        text = str(template)
        for key, desc in params.items():
            if isinstance(desc, dict) and "default" in desc:
                text = text.replace("{" + key + "}", str(desc["default"]))
        return text

    @staticmethod
    async def _emit(cb, payload: Dict[str, Any]) -> None:
        if cb is None:
            return
        try:
            result = cb(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # noqa: BLE001
            pass