import 'package:flutter_test/flutter_test.dart';
import 'package:ar_live2d_agent/core/net/ws_frame.dart';

void main() {
  setUp(() => WsFrame.nextEpoch());

  test('信封结构含 type/data/request_id/stream_id/timestamp', () {
    final Map<String, dynamic> e = WsFrame.envelope(
      type: 'device.stage_event',
      data: <String, dynamic>{'action': 'fling_out'},
      clientId: 'client_1',
      requestId: 'm-stage-1',
      streamId: 'stage-1',
    );
    expect(e['type'], 'device.stage_event');
    expect((e['data'] as Map<String, dynamic>)['client_id'], 'client_1');
    expect((e['data'] as Map<String, dynamic>)['action'], 'fling_out');
    expect(e.containsKey('request_id'), isTrue);
    expect(e.containsKey('stream_id'), isTrue);
    expect(e.containsKey('timestamp'), isTrue);
    // release 下不得出现调试字段（U55）
    expect((e['data'] as Map<String, dynamic>).containsKey('debug'), isFalse);
  });

  test('重连后 epoch 递增且 seq 归零', () {
    final int before = WsFrame.epoch;
    WsFrame.nextSeq();
    WsFrame.nextEpoch();
    expect(WsFrame.epoch, before + 1);
    expect(WsFrame.nextSeq(), 1);
  });
}
