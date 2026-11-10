import 'package:companion_mobile/core/network/api.dart';
import 'package:companion_mobile/core/storage/local_store.dart';
import 'package:companion_mobile/core/network/sse.dart';
import 'package:companion_mobile/features/chat/application/chat_controller.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class UncertainSendApi extends Api {
  UncertainSendApi(super.store);
  final sentIds = <String>[];
  @override
  Future<Json> post(String path, [dynamic data]) async {
    sentIds.add((data as Json)['client_message_id'] as String);
    throw StateError('响应丢失');
  }
}

class ReconnectApi extends Api {
  ReconnectApi(super.store);
  final subscribedRuns = <String>[];
  final afterSequences = <int>[];
  bool completed = false;
  int posts = 0;
  Json get assistant => {
    'id': 'assistant',
    'seq': 2,
    'role': 'assistant',
    'status': completed ? 'completed' : 'pending',
    'content': completed ? '已检查的回复' : '',
  };
  @override
  Future<Json> get(String path, {Json? query}) async {
    if (path == '/conversations') {
      return {
        'items': [
          {'id': 'conversation'},
        ],
      };
    }
    if (path == '/conversations/conversation') {
      return {'active_run_id': 'original-run'};
    }
    if (path.endsWith('/messages')) {
      return {
        'items': [
          {'id': 'user', 'seq': 1, 'role': 'user', 'content': '您好'},
          assistant,
        ],
      };
    }
    if (path == '/runs/original-run') {
      return {
        'status': completed ? 'completed' : 'generating',
        'last_event_seq': completed ? 3 : 1,
        'assistant_message': assistant,
      };
    }
    throw StateError('unexpected path $path');
  }

  @override
  Future<Json> post(String path, [dynamic data]) async {
    posts++;
    return {};
  }

  @override
  Stream<ServerEvent> events(
    String runId,
    int afterSeq,
    CancelToken cancelToken,
  ) async* {
    subscribedRuns.add(runId);
    afterSequences.add(afterSeq);
    yield const ServerEvent(
      type: 'status',
      data: '{"seq":2,"phase":"generating"}',
    );
    if (subscribedRuns.length == 1) throw StateError('network disconnected');
    completed = true;
    yield const ServerEvent(
      type: 'message.completed',
      data: '{"seq":3,"message_id":"assistant","content":"已检查的回复"}',
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'uncertain sends reuse UUID and persist metadata without body',
    () async {
      SharedPreferences.setMockInitialValues({});
      final store = LocalStore(await SharedPreferences.getInstance());
      final api = UncertainSendApi(store);
      final chat = ChatController(api, 'persona')
        ..conversationId = 'conversation';
      expect(await chat.send('我的私人资料'), isFalse);
      expect(await chat.resend(), isFalse);
      expect(api.sentIds[0], api.sentIds[1]);
      final saved = store.recovery('persona')!;
      expect(saved['client_message_id'], api.sentIds.first);
      expect(saved.toString(), isNot(contains('我的私人资料')));
      expect(
        saved.keys,
        unorderedEquals([
          'conversation_id',
          'run_id',
          'last_event_seq',
          'client_message_id',
        ]),
      );
      chat.dispose();
      api.dispose();
    },
  );
  test(
    'history snapshots replace message IDs and sort server sequences',
    () async {
      SharedPreferences.setMockInitialValues({});
      final api = UncertainSendApi(
        LocalStore(await SharedPreferences.getInstance()),
      );
      final chat = ChatController(api, 'persona');
      chat.mergeMessages([
        {'id': 'b', 'seq': 2, 'content': ''},
        {'id': 'a', 'seq': 1, 'content': '用户'},
      ]);
      chat.mergeMessages([
        {'id': 'b', 'seq': 2, 'content': '完整回复'},
      ]);
      expect(chat.messages.map((m) => m['id']), ['a', 'b']);
      expect(chat.messages.last['content'], '完整回复');
      chat.dispose();
      api.dispose();
    },
  );
  test(
    'disconnect replays same run and does not submit another generation',
    () async {
      SharedPreferences.setMockInitialValues({});
      final api = ReconnectApi(
        LocalStore(await SharedPreferences.getInstance()),
      );
      final chat = ChatController(api, 'persona');
      await chat.initialize();
      final deadline = DateTime.now().add(const Duration(seconds: 4));
      while (chat.status != 'completed' && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      expect(chat.status, 'completed');
      expect(api.subscribedRuns, ['original-run', 'original-run']);
      expect(api.afterSequences, [1, 2]);
      expect(api.posts, 0);
      expect(chat.messages.where((m) => m['id'] == 'assistant'), hasLength(1));
      expect(chat.messages.last['content'], '已检查的回复');
      chat.dispose();
      api.dispose();
    },
  );
}
