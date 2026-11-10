import 'dart:async';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../../../core/network/api.dart';
import '../../../core/network/sse.dart';

class ChatController extends ChangeNotifier {
  ChatController(this.api, this.personaId);
  final Api api;
  final String personaId;
  final messages = <Json>[];
  final cursor = EventCursor();
  String? conversationId;
  String? runId;
  String status = '';
  String connection = '正在连接';
  String? error;
  int? beforeSeq;
  bool loading = true;
  bool submitting = false;
  bool loadingOlder = false;
  String? _pendingText;
  String? _pendingId;
  String? _retryOf;
  bool _disposed = false;
  bool _watching = false;
  int _watchGeneration = 0;
  CancelToken? _streamCancel;
  Timer? _poll;
  bool _polling = false;
  bool get active => runId != null && !isRunTerminal(status);
  bool get canResend =>
      _pendingId != null && _pendingText != null && !submitting;
  String? get pendingText => _pendingText;

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> _persist() => api.store.saveRecovery(personaId, {
    'conversation_id': conversationId,
    'run_id': runId,
    'last_event_seq': cursor.sequence,
    'client_message_id': _pendingId,
  });

  Future<void> initialize({
    String? selectedConversation,
    bool newConversation = false,
  }) async {
    _watchGeneration++;
    _streamCancel?.cancel();
    _poll?.cancel();
    _watching = false;
    messages.clear();
    runId = null;
    status = '';
    beforeSeq = null;
    cursor.sequence = 0;
    loading = true;
    error = null;
    _changed();
    try {
      final saved = api.store.recovery(personaId);
      conversationId =
          selectedConversation ??
          (newConversation ? null : saved?['conversation_id'] as String?);
      if (conversationId == null && !newConversation) {
        final list = await api.list(
          '/conversations',
          query: {'persona_id': personaId, 'limit': 20},
        );
        if (list.isNotEmpty) conversationId = list.first['id'] as String;
      }
      if (conversationId == null) {
        final conversation = await api.post('/conversations', {
          'persona_id': personaId,
        });
        conversationId = conversation['id'] as String;
      }
      final conversation = await api.get('/conversations/$conversationId');
      await refreshMessages();
      runId =
          (conversation['active_run_id'] ?? conversation['latest_run_id'])
              as String?;
      if (runId == null && saved?['conversation_id'] == conversationId) {
        runId = saved?['run_id'] as String?;
      }
      if (saved?['run_id'] == runId &&
          saved?['conversation_id'] == conversationId) {
        cursor.sequence = (saved?['last_event_seq'] as num?)?.toInt() ?? 0;
      }
      if (runId != null) await snapshot();
      await _persist();
      _startWatch();
    } catch (e) {
      if (e is DioException &&
          e.response?.statusCode == 404 &&
          selectedConversation == null &&
          !newConversation) {
        await api.store.clearRecovery(personaId);
        await initialize(newConversation: true);
        return;
      }
      error = errorMessage(e);
    }
    loading = false;
    _changed();
  }

  void mergeMessages(List<Json> incoming) {
    final byId = {
      for (final message in messages) message['id'] as String: message,
    };
    for (final message in incoming) {
      final existing = byId[message['id']];
      if (existing != null &&
          existing['status'] == 'completed' &&
          message['status'] == 'pending') {
        continue;
      }
      byId[message['id'] as String] = message;
    }
    messages
      ..clear()
      ..addAll(
        byId.values.toList()
          ..sort((a, b) => (a['seq'] as num).compareTo(b['seq'] as num)),
      );
  }

  Future<void> refreshMessages() async {
    final page = await api.get(
      '/conversations/$conversationId/messages',
      query: {'limit': 50},
    );
    mergeMessages((page['items'] as List).cast<Json>());
    beforeSeq = (page['next_before_seq'] as num?)?.toInt();
  }

  Future<void> older() async {
    if (beforeSeq == null || loadingOlder) return;
    loadingOlder = true;
    _changed();
    try {
      final page = await api.get(
        '/conversations/$conversationId/messages',
        query: {'limit': 50, 'before_seq': beforeSeq},
      );
      mergeMessages((page['items'] as List).cast<Json>());
      beforeSeq = (page['next_before_seq'] as num?)?.toInt();
    } catch (e) {
      error = errorMessage(e);
    }
    loadingOlder = false;
    _changed();
  }

  Future<bool> send(String text) async {
    if (submitting || active || text.trim().isEmpty) return false;
    if (_pendingText != null && _pendingText != text) {
      error = '上一条消息尚未确认，请先重发或放弃。';
      _changed();
      return false;
    }
    _pendingText ??= text;
    _pendingId ??= const Uuid().v4();
    _retryOf = null;
    return _submit();
  }

  Future<bool> resend() => _submit();
  void discardPending() {
    _pendingId = null;
    _pendingText = null;
    _retryOf = null;
    unawaited(_persist());
    error = null;
    _changed();
  }

  Future<bool> retry() async {
    if (active || submitting || runId == null) return false;
    _retryOf ??= runId;
    _pendingId ??= const Uuid().v4();
    _pendingText ??=
        messages.where((m) => m['role'] == 'user').lastOrNull?['content']
            as String? ??
        '';
    return _submit();
  }

  Future<bool> _submit() async {
    if (submitting || _pendingId == null || conversationId == null) {
      return false;
    }
    submitting = true;
    error = null;
    _changed();
    await _persist(); // Persist identity before network dispatch, never a body cache.
    try {
      final result = _retryOf == null
          ? await api.post('/conversations/$conversationId/runs', {
              'client_message_id': _pendingId,
              'text': _pendingText,
            })
          : await api.post('/runs/$_retryOf/retry', {
              'client_message_id': _pendingId,
            });
      _watchGeneration++;
      _streamCancel?.cancel();
      _poll?.cancel();
      _watching = false;
      runId = result['run_id'] as String;
      status = result['status'] as String;
      cursor.sequence = 0;
      _pendingId = null;
      _pendingText = null;
      _retryOf = null;
      await _persist();
      _startWatch();
      try {
        await refreshMessages();
      } catch (_) {
        error = '消息已发送，历史暂未同步；正在恢复连接。';
      }
      return true;
    } catch (e) {
      error = errorMessage(e);
      return false;
    } finally {
      submitting = false;
      _changed();
    }
  }

  Future<void> snapshot() async {
    final current = runId;
    if (current == null) return;
    final result = await api.get('/runs/$current');
    if (_disposed || runId != current) return;
    final incomingStatus = result['status'] as String;
    if (isRunTerminal(status) && !isRunTerminal(incomingStatus)) return;
    status = incomingStatus;
    final finalMessage = result['assistant_message'];
    if (finalMessage is Map<String, dynamic>) mergeMessages([finalMessage]);
    // The snapshot contains authoritative status/full body, so skipping replayed
    // progress up to this cursor is safe even after EVENTS_EXPIRED.
    cursor.sequence = max(
      cursor.sequence,
      (result['last_event_seq'] as num?)?.toInt() ?? 0,
    );
    if (isRunTerminal(status)) {
      try {
        await refreshMessages();
      } catch (_) {
        error = '回复状态已同步，部分历史稍后恢复。';
      }
    }
    await _persist();
    _changed();
  }

  void _startWatch() {
    if (_disposed || !active || _watching) return;
    _watching = true;
    final generation = ++_watchGeneration;
    _poll?.cancel();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) async {
      if (_polling || _disposed || !active) return;
      _polling = true;
      try {
        await snapshot();
      } catch (_) {
        /* SSE/reconnect reports the error. */
      } finally {
        _polling = false;
      }
    });
    unawaited(_watch(generation));
  }

  Future<void> _watch(int generation) async {
    var attempt = 0;
    final watchedRun = runId;
    try {
      while (!_disposed && active && generation == _watchGeneration) {
        _streamCancel = CancelToken();
        try {
          connection = attempt == 0 ? '已连接' : '正在重连';
          _changed();
          await for (final event in api.events(
            watchedRun!,
            cursor.sequence,
            _streamCancel!,
          )) {
            if (_disposed ||
                generation != _watchGeneration ||
                runId != watchedRun) {
              break;
            }
            final body = event.json;
            final seq =
                (body['seq'] as num?)?.toInt() ??
                int.tryParse(event.id ?? '') ??
                0;
            cursor.apply(seq, () {
              if (event.type == 'status') {
                status = (body['phase'] ?? body['status'] ?? status) as String;
              }
              if (event.type == 'message.completed') {
                status = 'completed';
                final messageId = body['message_id'];
                final index = messages.indexWhere((m) => m['id'] == messageId);
                if (index >= 0 && body['content'] is String) {
                  messages[index] = {
                    ...messages[index],
                    'content': body['content'],
                    'status': 'completed',
                  };
                }
              }
              if (event.type.startsWith('run.')) {
                status = event.type.substring(4);
              }
            });
            attempt = 0;
            connection = '已连接';
            await _persist();
            _changed();
            if (!active) break;
          }
          if (_disposed ||
              generation != _watchGeneration ||
              runId != watchedRun) {
            break;
          }
          await snapshot();
          if (!active) break;
        } catch (e) {
          if (_disposed || generation != _watchGeneration) break;
          if (e is DioException && e.response?.statusCode == 410) {
            try {
              await snapshot();
            } catch (_) {
              /* retry below */
            }
          }
          connection = '连接中断，正在恢复';
          _changed();
        }
        if (!_disposed && active) {
          final delay = min(8, 1 << min(attempt++, 3));
          await Future<void>.delayed(
            Duration(milliseconds: delay * 1000 + Random().nextInt(300)),
          );
        }
      }
    } finally {
      if (generation == _watchGeneration) {
        _watching = false;
        _poll?.cancel();
        connection = isRunTerminal(status) ? '已同步' : '连接中断';
        _changed();
      }
    }
  }

  Future<void> resume() async {
    try {
      await snapshot();
      error = null;
      _startWatch();
    } catch (e) {
      error = errorMessage(e);
    }
    _changed();
  }

  Future<void> cancel() async {
    if (!active) return;
    try {
      await api.post('/runs/$runId/cancel');
      await snapshot();
    } catch (e) {
      error = errorMessage(e);
    }
    _changed();
  }

  @override
  void dispose() {
    _disposed = true;
    _watchGeneration++;
    _streamCancel?.cancel();
    _poll?.cancel();
    super.dispose();
  }
}
