import 'package:flutter/material.dart';

import '../app/gal_palette.dart';
import '../app/routes.dart';
import '../app/stage_scope.dart';
import '../core/config/app_config.dart';
import '../core/net/ws_url.dart';
import '../services/storage/prefs.dart';
import '../components/common/gal_page.dart';
import '../components/common/retry_hint.dart';
import '../components/common/section_card.dart';

/// 手动输入串流地址：全屏新页面，不再用 AlertDialog。
/// 支持 ws(s)://host:port/、?uid= 配对、JSON 二维码内容。
class ConnectPage extends StatefulWidget {
  const ConnectPage({super.key});

  @override
  State<ConnectPage> createState() => _ConnectPageState();
}

class _ConnectPageState extends State<ConnectPage> {
  late final TextEditingController _url = TextEditingController(
    text: AppConfig.suggestedWsUrl,
  );
  late final TextEditingController _uid = TextEditingController();
  String _error = '';
  String? _lastUrl;

  @override
  void initState() {
    super.initState();
    Prefs.getLastWsUrl().then((String? value) {
      if (mounted && value != null && value.isNotEmpty) {
        setState(() => _lastUrl = value);
      }
    });
  }

  @override
  void dispose() {
    _url.dispose();
    _uid.dispose();
    super.dispose();
  }

  WsEndpoint? _parse() {
    final String raw = _url.text.trim();
    if (raw.isEmpty) {
      setState(() => _error = '请填写串流地址，或返回扫码页');
      return null;
    }
    final WsEndpoint? endpoint = WsUrl.parse(raw);
    if (endpoint == null) {
      setState(() => _error = '地址格式无效，请重试');
      return null;
    }
    final String uid = _uid.text.trim();
    setState(() => _error = '');
    return uid.isEmpty ? endpoint : WsEndpoint(endpoint.url, uid: uid);
  }

  Future<void> _connect({bool gotoStage = true}) async {
    final WsEndpoint? endpoint = _parse();
    if (endpoint == null) return;
    final session = StageScope.of(context);
    await session.reconnect(
      endpoint.hasUid
          ? '${endpoint.url}${endpoint.url.contains('?') ? '&' : '?'}uid=${endpoint.uid}'
          : endpoint.url,
    );
    if (!mounted) return;
    if (gotoStage) {
      await Navigator.of(context)
          .pushReplacementNamed(AppRoutes.stage, arguments: endpoint);
    } else {
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = StageScope.of(context);
    return GalPage(
      title: '连接电脑端',
      subtitle: '没有电脑端可直接返回，离线用系统识别继续演出',
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            SectionCard(
              title: '串流地址',
              children: <Widget>[
                TextField(
                  controller: _url,
                  keyboardType: TextInputType.url,
                  style: TextStyle(
                    color: GalPalette.of(context).text,
                    fontSize: 12,
                  ),
                  decoration: InputDecoration(
                    labelText: 'ws://192.168.1.10:8000/',
                    labelStyle: TextStyle(
                      color: GalPalette.of(context).textFaint,
                      fontSize: 11,
                    ),
                    enabledBorder: UnderlineInputBorder(
                      borderSide: BorderSide(
                        color: GalPalette.of(context).border,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: _uid,
                  style: TextStyle(
                    color: GalPalette.of(context).text,
                    fontSize: 12,
                  ),
                  decoration: InputDecoration(
                    labelText: '配对 uid（可选，与电脑端二维码一致）',
                    labelStyle: TextStyle(
                      color: GalPalette.of(context).textFaint,
                      fontSize: 11,
                    ),
                    enabledBorder: UnderlineInputBorder(
                      borderSide: BorderSide(
                        color: GalPalette.of(context).border,
                      ),
                    ),
                  ),
                ),
                if (_error.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 10),
                  RetryHint(
                    compact: true,
                    title: '连接失败',
                    detail: _error,
                    onRetry: () => _connect(gotoStage: false),
                  ),
                ],
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: <Widget>[
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: GalPalette.of(context).cardAlt,
                        foregroundColor: GalPalette.of(context).accent,
                      ),
                      onPressed: () => _connect(),
                      icon: const Icon(Icons.cable, size: 15),
                      label: const Text(
                        '连接并进入舞台',
                        style: TextStyle(fontSize: 12),
                      ),
                    ),
                    TextButton.icon(
                      onPressed: () => _connect(gotoStage: false),
                      icon: const Icon(Icons.refresh, size: 14),
                      label: const Text('仅重连', style: TextStyle(fontSize: 11)),
                    ),
                  ],
                ),
              ],
            ),
            if (_lastUrl != null)
              SectionCard(
                title: '上次连接',
                children: <Widget>[
                  Text(
                    _lastUrl!,
                    style: TextStyle(
                      color: GalPalette.of(context).textDim,
                      fontSize: 11,
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: () {
                      _url.text = _lastUrl!;
                      setState(() {});
                    },
                    icon: const Icon(Icons.history, size: 14),
                    label: const Text('填入地址', style: TextStyle(fontSize: 11)),
                  ),
                ],
              ),
            SectionCard(
              title: '当前状态',
              children: <Widget>[
                AnimatedBuilder(
                  animation: session,
                  builder: (_, _) => Text(
                    '${session.ws.state.name} · '
                    '${session.ws.isRegistered ? '已绑定' : '未绑定'} · '
                    '${session.asrEngineLabel}',
                    style: TextStyle(
                      color: GalPalette.of(context).textDim,
                      fontSize: 11,
                    ),
                  ),
                ),
                const SizedBox(height: 6),
                ValueListenableBuilder<String>(
                  valueListenable: session.hint,
                  builder: (_, String hint, _) => Text(
                    hint,
                    style: TextStyle(
                      color: GalPalette.of(context).textFaint,
                      fontSize: 11,
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                RetryHint(
                  compact: true,
                  title: '没有电脑端？',
                  detail: '点右上角返回扫码页再「跳过」，或直接在离线舞台使用系统内置语音识别。',
                  actionLabel: '请重试',
                  onRetry: () => Navigator.of(context).maybePop(),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
