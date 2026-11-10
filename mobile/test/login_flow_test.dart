import 'package:companion_mobile/app/app.dart';
import 'package:companion_mobile/app/providers.dart';
import 'package:companion_mobile/core/network/api.dart';
import 'package:companion_mobile/core/storage/local_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class LoginStore extends LocalStore {
  LoginStore(super.preferences);
  @override
  Future<void> saveTokens(String access, String refresh) async {}
}

class LoginApi extends Api {
  LoginApi(super.store);
  Json? verified;
  @override
  Future<Json> publicPost(String path, Json data) async {
    if (path.endsWith('/request')) {
      return {'challenge_id': 'challenge', 'development_code': '123456'};
    }
    verified = data;
    return {'access_token': 'access', 'refresh_token': 'refresh'};
  }

  @override
  Future<Json> get(String path, {Json? query}) async => {'items': []};
}

void main() {
  testWidgets(
    'OTP verifies original challenge and opens authenticated persona list',
    (tester) async {
      tester.view.physicalSize = const Size(640, 1100);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      SharedPreferences.setMockInitialValues({});
      final store = LoginStore(await SharedPreferences.getInstance());
      final api = LoginApi(store);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            localStoreProvider.overrideWithValue(store),
            apiProvider.overrideWith((ref) => api),
          ],
          child: const CompanionApp(),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('慢慢说，我听着'), findsOneWidget);
      await tester.enterText(find.byType(TextField).first, '13800000000');
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('获取验证码'));
      await tester.tap(find.text('获取验证码'));
      await tester.pumpAndSettle();
      expect(find.text('开发环境验证码：123456'), findsOneWidget);
      await tester.enterText(find.byType(TextField).last, '123456');
      await tester.ensureVisible(find.text('登录并开始'));
      await tester.tap(find.text('登录并开始'));
      await tester.pumpAndSettle();
      expect(api.verified, {
        'phone': '13800000000',
        'code': '123456',
        'challenge_id': 'challenge',
      });
      expect(find.text('今天，聊一聊'), findsOneWidget);
      expect(find.textContaining('这是 AI 陪伴助手'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
