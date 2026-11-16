import 'package:flutter/material.dart';

import '../../app/gal_palette.dart';
import '../../app/stage_session.dart';
import '../../core/config/app_config.dart';
import '../../core/input/text_merge.dart';
import '../common/retry_hint.dart';

/// 对话历史内容（不再是弹窗）：内存环形队列上限 100 条、可搜索、可清空。
/// 历史页与旧调用点共用它；无历史显示蓝色 galgame 风格的「请重试」。
class HistoryLayer extends StatefulWidget {
  const HistoryLayer({
    super.key,
    required this.session,
    this.onClose,
    this.searchable = true,
  });

  final StageSession session;
  final VoidCallback? onClose;
  final bool searchable;

  @override
  State<HistoryLayer> createState() => _HistoryLayerState();
}

class _HistoryLayerState extends State<HistoryLayer> {
  final TextEditingController _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<String> get _items {
    final List<String> all = widget.session.history;
    final int count = all.length > AppConfig.maxHistoryItems
        ? AppConfig.maxHistoryItems
        : all.length;
    final String q = _search.text.trim().toLowerCase();
    final List<String> slice = all.sublist(all.length - count);
    final Iterable<String> filtered = q.isEmpty
        ? slice
        : slice.where((String s) => s.toLowerCase().contains(q));
    // 相邻去重兜底：即便旧数据里已有连续重复，列表也不显示两遍。
    return dedupeAdjacent(filtered);
  }

  @override
  Widget build(BuildContext context) {
    final StageSession session = widget.session;
    final List<String> items = _items;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (widget.searchable) ...<Widget>[
          TextField(
            controller: _search,
            style: TextStyle(color: GalPalette.of(context).text, fontSize: 12),
            decoration: InputDecoration(
              hintText: '搜索台词…',
              hintStyle: TextStyle(
                color: GalPalette.of(context).textFaint,
                fontSize: 11,
              ),
              prefixIcon: Icon(
                Icons.search,
                color: GalPalette.of(context).textDim,
                size: 16,
              ),
              filled: true,
              fillColor: GalPalette.of(context).dialog,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: GalPalette.of(context).border),
              ),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 10),
        ],
        if (items.isEmpty)
          RetryHint(
            title: session.history.isEmpty ? '尚无对话记录' : '没有匹配的记录',
            detail: session.history.isEmpty
                ? '没有历史也应能继续：请重试，或回到舞台说点什么吧。'
                : '换个关键词，或点「请重试」重发最后一条输入。',
            onRetry: () {
              widget.onClose?.call();
              session.retryLast();
            },
          )
        else
          ListView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: items.length,
            itemBuilder: (_, int i) => Container(
              margin: const EdgeInsets.only(bottom: 6),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: GalPalette.of(context).card.withValues(alpha: .85),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: GalPalette.of(context).borderSoft),
              ),
              child: Text(
                items[i],
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: GalPalette.of(context).textDim,
                  fontSize: 12,
                ),
              ),
            ),
          ),
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: <Widget>[
            TextButton.icon(
              onPressed: () {
                session.clearHistory();
                setState(() {});
              },
              icon: const Icon(Icons.delete_outline, size: 14),
              label: const Text('清空', style: TextStyle(fontSize: 11)),
            ),
            if (widget.onClose != null)
              TextButton(
                onPressed: widget.onClose,
                child: const Text('返回舞台', style: TextStyle(fontSize: 11)),
              ),
          ],
        ),
      ],
    );
  }
}
