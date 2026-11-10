import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/login_page.dart';
import '../features/chat/chat_page.dart';
import '../features/memories/memories_page.dart';
import '../features/personas/persona_editor_page.dart';
import '../features/personas/personas_page.dart';
import '../features/settings/settings_page.dart';
import 'providers.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final api = ref.read(apiProvider);
  final router = GoRouter(
    refreshListenable: api,
    redirect: (context, state) {
      if (!api.signedIn) {
        return state.matchedLocation == '/login' ? null : '/login';
      }
      return state.matchedLocation == '/login' ? '/' : null;
    },
    routes: [
      GoRoute(path: '/login', builder: (context, state) => const LoginPage()),
      GoRoute(
        path: '/',
        builder: (context, state) => PersonasPage(key: state.pageKey),
      ),
      GoRoute(
        path: '/settings',
        builder: (context, state) => const SettingsPage(),
      ),
      GoRoute(
        path: '/personas/new',
        builder: (context, state) => const PersonaEditorPage(),
      ),
      GoRoute(
        path: '/personas/:id/edit',
        builder: (context, state) =>
            PersonaEditorPage(personaId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/personas/:id/preview',
        builder: (context, state) =>
            PreviewPage(personaId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/personas/:id/chat',
        builder: (context, state) => ChatPage(
          personaId: state.pathParameters['id']!,
          conversationId: state.uri.queryParameters['conversation'],
          newConversation: state.uri.queryParameters['new'] == '1',
        ),
      ),
      GoRoute(
        path: '/personas/:id/history',
        builder: (context, state) =>
            ConversationHistoryPage(personaId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/personas/:id/memories',
        builder: (context, state) =>
            MemoriesPage(personaId: state.pathParameters['id']!),
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

class CompanionApp extends ConsumerWidget {
  const CompanionApp({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final large = ref.watch(largeTextProvider);
    final colors = ColorScheme.fromSeed(
      seedColor: const Color(0xff416b56),
      surface: const Color(0xfff8f6f0),
    );
    return MaterialApp.router(
      title: '慢慢说 · AI 陪伴',
      debugShowCheckedModeBanner: false,
      locale: const Locale('zh', 'CN'),
      supportedLocales: const [Locale('zh', 'CN')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      routerConfig: ref.watch(routerProvider),
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: colors,
        scaffoldBackgroundColor: colors.surface,
        textTheme: const TextTheme(
          bodyLarge: TextStyle(fontSize: 18, height: 1.55),
          bodyMedium: TextStyle(fontSize: 17, height: 1.55),
          labelLarge: TextStyle(fontSize: 17),
          titleLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
        ),
        inputDecorationTheme: InputDecorationTheme(
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
          filled: true,
          fillColor: Colors.white,
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(minimumSize: const Size(48, 52)),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(minimumSize: const Size(48, 52)),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
        ),
      ),
      builder: (context, child) {
        final media = MediaQuery.of(context);
        return MediaQuery(
          data: media.copyWith(
            textScaler: TextScaler.linear(
              media.textScaler.scale(1) * (large ? 1.15 : 1),
            ),
          ),
          child: child!,
        );
      },
    );
  }
}
