import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/network/api.dart';
import '../core/storage/local_store.dart';
import '../features/chat/application/chat_controller.dart';

final localStoreProvider = Provider<LocalStore>(
  (ref) => throw UnimplementedError(),
);
final apiProvider = ChangeNotifierProvider<Api>(
  (ref) => throw UnimplementedError(),
);
final largeTextProvider = StateProvider<bool>(
  (ref) => ref.watch(localStoreProvider).largeText,
);
final personasRevisionProvider = StateProvider<int>((ref) => 0);
final chatProvider = ChangeNotifierProvider.autoDispose
    .family<ChatController, String>((ref, id) {
      return ChatController(ref.read(apiProvider), id);
    });
