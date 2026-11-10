import 'dart:async';
import 'dart:typed_data';

import 'package:companion_mobile/core/network/api.dart';
import 'package:companion_mobile/core/storage/local_store.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class MemoryStore extends LocalStore {
  MemoryStore(super.preferences);
  String? savedAccess;
  @override
  Future<void> saveTokens(String access, String refresh) async {
    savedAccess = access;
  }
}

class FakeAdapter implements HttpClientAdapter {
  int refreshes = 0;
  int oldRequests = 0;
  final bothOld = Completer<void>();
  final bodies = <Object?>[];
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (options.path.endsWith('/auth/refresh')) {
      refreshes++;
      await bothOld.future;
      return ResponseBody.fromString(
        '{"access_token":"new","refresh_token":"new-refresh"}',
        200,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    }
    bodies.add(options.data);
    if (options.headers['Authorization'] == 'Bearer old') {
      if (++oldRequests == 2) bothOld.complete();
      return ResponseBody.fromString(
        '{}',
        401,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    }
    return ResponseBody.fromString(
      '{"ok":true}',
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'concurrent 401 rotates once and retransmits identical client identities',
    () async {
      SharedPreferences.setMockInitialValues({});
      final store = MemoryStore(await SharedPreferences.getInstance());
      final adapter = FakeAdapter();
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test'))
        ..httpClientAdapter = adapter;
      final api = Api(store, transport: dio)
        ..accessToken = 'old'
        ..refreshToken = 'old-refresh';
      final body = {'client_message_id': 'stable-id', 'text': '您好'};
      final results = await Future.wait([
        api.post('/conversations/one/runs', body),
        api.post('/conversations/two/runs', body),
      ]);
      expect(results.every((r) => r['ok'] == true), isTrue);
      expect(adapter.refreshes, 1);
      expect(store.savedAccess, 'new');
      expect(adapter.bodies, everyElement(same(body)));
      api.dispose();
      dio.close();
    },
  );
}
