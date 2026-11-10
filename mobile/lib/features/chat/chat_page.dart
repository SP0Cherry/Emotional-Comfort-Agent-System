import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/providers.dart';
import '../../app/widgets.dart';
import '../../core/network/api.dart';
import 'application/chat_controller.dart';

String runLabel(String status) => switch (status) {
  'queued' => '正在等待回复',
  'preparing' => '正在理解您的话',
  'generating' => '正在准备回复',
  'reviewing' => '正在检查回复',
  'failed' => '这次回复未完成',
  'cancelled' => '回复已停止',
  'interrupted' => '回复被中断',
  'completed' => '回复已完成',
  _ => '正在回复',
};

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({
    required this.personaId,
    this.conversationId,
    this.newConversation = false,
    super.key,
  });
  final String personaId;
  final String? conversationId;
  final bool newConversation;
  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage>
    with WidgetsBindingObserver {
  final _input = TextEditingController();
  String _name = 'AI 陪伴';
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(() async {
      final controller = ref.read(chatProvider(widget.personaId));
      unawaited(
        controller.initialize(
          selectedConversation: widget.conversationId,
          newConversation: widget.newConversation,
        ),
      );
      try {
        final person = await ref
            .read(apiProvider)
            .get('/personas/${widget.personaId}');
        if (mounted) setState(() => _name = person['display_name'] as String);
      } catch (_) {
        /* Chat errors use their own visible error/retry controls. */
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(ref.read(chatProvider(widget.personaId)).resume());
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _input.dispose();
    super.dispose();
  }

  Future<void> _send(ChatController chat, {bool resend = false}) async {
    final text = _input.text;
    final pending = chat.pendingText;
    final accepted = resend ? await chat.resend() : await chat.send(text);
    if (accepted && mounted && _input.text == (resend ? pending : text)) {
      _input.clear();
    }
  }

  Future<void> _end(ChatController chat) async {
    if (chat.active) {
      final confirmed = await confirmAction(
        context,
        '结束本次对话？',
        '会停止当前回复。已保存的聊天和记忆仍可查看。',
        '停止并结束',
      );
      if (!confirmed) return;
      await chat.cancel();
      if (chat.error != null) return;
    }
    if (mounted) Navigator.pop(context);
  }

  Widget _message(Json message) {
    final mine = message['role'] == 'user';
    final complete = message['status'] == 'completed';
    final content = message['content'] as String? ?? '';
    return Align(
      key: ValueKey(message['id']),
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 7),
        padding: const EdgeInsets.all(16),
        constraints: const BoxConstraints(maxWidth: 640),
        decoration: BoxDecoration(
          color: mine
              ? Theme.of(context).colorScheme.primaryContainer
              : Colors.white,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: const Color(0xffdde2da)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              mine ? '我' : 'AI 陪伴',
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const SizedBox(height: 6),
            if (mine || complete)
              SelectableText(content)
            else
              Text(
                runLabel(message['status'] as String? ?? ''),
                style: const TextStyle(fontStyle: FontStyle.italic),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final chat = ref.watch(chatProvider(widget.personaId));
    return Scaffold(
      appBar: AppBar(
        title: Text(_name),
        actions: [
          TextButton(onPressed: () => _end(chat), child: const Text('结束对话')),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: IdentityNotice(),
            ),
            if (chat.loading) const LinearProgressIndicator(),
            Expanded(
              child: chat.messages.isEmpty && !chat.loading
                  ? const Center(
                      child: Padding(
                        padding: EdgeInsets.all(28),
                        child: Text(
                          '今天过得怎么样？\n您可以从一句想说的话开始。',
                          textAlign: TextAlign.center,
                        ),
                      ),
                    )
                  : ListView.builder(
                      reverse: true,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 8,
                      ),
                      itemCount:
                          chat.messages.length +
                          (chat.beforeSeq != null ? 1 : 0),
                      itemBuilder: (context, index) {
                        if (index == chat.messages.length) {
                          return TextButton(
                            onPressed: chat.loadingOlder ? null : chat.older,
                            child: Text(chat.loadingOlder ? '正在加载' : '查看更早的消息'),
                          );
                        }
                        return _message(
                          chat.messages[chat.messages.length - index - 1],
                        );
                      },
                    ),
            ),
            if (chat.error != null)
              ErrorNotice(
                chat.error!,
                retry: chat.loading || chat.submitting
                    ? null
                    : () => chat.conversationId == null
                          ? chat.initialize(
                              newConversation: widget.newConversation,
                            )
                          : chat.resume(),
              ),
            if (chat.canResend)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Wrap(
                  spacing: 8,
                  children: [
                    FilledButton(
                      onPressed: () => _send(chat, resend: true),
                      child: const Text('重新提交同一条消息'),
                    ),
                    TextButton(
                      onPressed: chat.discardPending,
                      child: const Text('放弃重发'),
                    ),
                  ],
                ),
              ),
            if (!chat.active &&
                const {
                  'failed',
                  'cancelled',
                  'interrupted',
                }.contains(chat.status) &&
                !chat.canResend)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: OutlinedButton(
                  onPressed: chat.submitting ? null : chat.retry,
                  child: const Text('重试这次回复'),
                ),
              ),
            if (chat.active)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        '${runLabel(chat.status)}\n${chat.connection}',
                      ),
                    ),
                    OutlinedButton(
                      onPressed: chat.cancel,
                      child: const Text('停止'),
                    ),
                  ],
                ),
              ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  TextField(
                    controller: _input,
                    minLines: 1,
                    maxLines: 4,
                    maxLength: 2000,
                    decoration: const InputDecoration(
                      labelText: '想说的话',
                      hintText: '慢慢写，不着急',
                    ),
                    enabled: !chat.loading,
                    textInputAction: TextInputAction.newline,
                  ),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed:
                          chat.loading ||
                              chat.active ||
                              chat.submitting ||
                              chat.canResend
                          ? null
                          : () => _send(chat),
                      icon: const Icon(Icons.send_rounded),
                      label: Text(chat.submitting ? '正在发送' : '发送'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
