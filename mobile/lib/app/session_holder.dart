import 'stage_session.dart';

/// 应用级唯一会话。
///
/// 设置 / 历史 / 连接 / 舞台都是独立命名路由，必须共享同一套
/// WebSocket / 状态机 / Live2D / 语音服务；全局单例避免每个页面重建服务，
/// 也避免把 session 塞进路由 arguments（Object 传递易丢失、难复用）。
final class SessionHolder {
  SessionHolder._();

  static final StageSession instance = StageSession();
}
