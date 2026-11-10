import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:companion_mobile/core/network/sse.dart';

void main() {
  test('UTF-8 characters and SSE frames survive every byte boundary', () async {
    final bytes = utf8.encode(
      ': ping\r\nid: 7\r\nevent: message.completed\r\ndata: {"seq":7,"content":"您好，慢慢说。"}\r\n\r\n',
    );
    for (var split = 0; split <= bytes.length; split++) {
      final events = await parseServerEvents(
        Stream.fromIterable([bytes.sublist(0, split), bytes.sublist(split)]),
      ).toList();
      expect(events, hasLength(1), reason: 'split=$split');
      expect(events.single.id, '7');
      expect(events.single.type, 'message.completed');
      expect(events.single.json['content'], '您好，慢慢说。');
    }
    final events = await parseServerEvents(
      Stream.fromIterable(bytes.map((byte) => [byte])),
    ).toList();
    expect(events.single.json['seq'], 7);
  });
  test('multiline data, BOM, comments and truncated frame', () async {
    final events = await parseServerEvents(
      Stream.value(
        utf8.encode(
          '\uFEFF: heartbeat\n\nevent: custom\nid: 2\ndata: 第一行\ndata: 第二行\n\ndata: incomplete',
        ),
      ),
    ).toList();
    expect(events, hasLength(1));
    expect(events.single.data, '第一行\n第二行');
  });
  test(
    'replay cursor deduplicates and advances only after successful apply',
    () {
      final cursor = EventCursor(4);
      var applied = 0;
      expect(cursor.apply(4, () => applied++), isFalse);
      expect(
        () =>
            cursor.apply(5, () => throw StateError('transient apply failure')),
        throwsStateError,
      );
      expect(cursor.sequence, 4);
      expect(cursor.apply(5, () => applied++), isTrue);
      expect(cursor.apply(5, () => applied++), isFalse);
      expect(applied, 1);
      expect(cursor.sequence, 5);
    },
  );
  test('all terminal statuses stop resubscription', () {
    for (final status in ['completed', 'failed', 'cancelled', 'interrupted']) {
      expect(isRunTerminal(status), isTrue);
    }
    expect(isRunTerminal('reviewing'), isFalse);
  });
}
