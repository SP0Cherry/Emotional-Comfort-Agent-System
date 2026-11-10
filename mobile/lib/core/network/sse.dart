import 'dart:async';
import 'dart:convert';

/// UTF-8 and lines both keep decoder state across network chunk boundaries.
/// An incomplete last frame is discarded; only a blank line commits an event.
class ServerEvent {
  const ServerEvent({required this.type, required this.data, this.id});
  final String type;
  final String data;
  final String? id;
  Map<String, dynamic> get json => jsonDecode(data) as Map<String, dynamic>;
}

Stream<ServerEvent> parseServerEvents(Stream<List<int>> bytes) async* {
  var event = 'message';
  String? id;
  final data = <String>[];
  var firstLine = true;
  await for (var line
      in bytes.transform(utf8.decoder).transform(const LineSplitter())) {
    if (firstLine) {
      line = line.replaceFirst(RegExp(r'^\uFEFF'), '');
      firstLine = false;
    }
    if (line.isEmpty) {
      if (data.isNotEmpty) {
        yield ServerEvent(type: event, data: data.join('\n'), id: id);
      }
      data.clear();
      event = 'message';
      id = null;
      continue;
    }
    if (line.startsWith(':')) continue;
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    switch (field) {
      case 'data':
        data.add(value);
      case 'event':
        event = value;
      case 'id':
        if (!value.contains('\u0000')) id = value;
    }
  }
}

bool isRunTerminal(String status) =>
    const {'completed', 'failed', 'cancelled', 'interrupted'}.contains(status);

/// Shared replay guard. Advance only after applying the complete event.
class EventCursor {
  EventCursor([this.sequence = 0]);
  int sequence;
  bool apply(int incoming, void Function() action) {
    if (incoming <= sequence) return false;
    action();
    sequence = incoming;
    return true;
  }
}
