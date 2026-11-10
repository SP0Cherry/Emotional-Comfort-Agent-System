import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app/app.dart';
import 'app/providers.dart';
import 'core/network/api.dart';
import 'core/storage/local_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    final store = LocalStore(await SharedPreferences.getInstance());
    final api = Api(store);
    await api.restore();
    runApp(
      ProviderScope(
        overrides: [
          localStoreProvider.overrideWithValue(store),
          apiProvider.overrideWith((ref) => api),
        ],
        child: const CompanionApp(),
      ),
    );
  } catch (_) {
    runApp(
      MaterialApp(
        home: Scaffold(
          body: SafeArea(
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      '暂时无法读取安全登录资料，或服务地址配置不正确。请重启应用；正式版本需配置 HTTPS 地址。',
                    ),
                    const SizedBox(height: 20),
                    FilledButton(onPressed: main, child: const Text('重新打开')),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
