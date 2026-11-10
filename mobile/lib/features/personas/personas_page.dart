import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/providers.dart';
import '../../app/widgets.dart';

class PersonasPage extends ConsumerWidget {
  const PersonasPage({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      title: const Text('今天，聊一聊'),
      actions: [
        TextButton(
          onPressed: () => context.push('/settings'),
          child: const Text('设置'),
        ),
      ],
    ),
    body: Column(
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 8, 20, 0),
          child: IdentityNotice(),
        ),
        Expanded(
          child: ResourceList(
            key: ValueKey(ref.watch(personasRevisionProvider)),
            path: '/personas',
            emptyText: '建立一位 AI 陪伴人物，设定您喜欢的称呼和说话方式。',
            itemBuilder: (context, person, reload) => Card(
              margin: const EdgeInsets.only(bottom: 16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Row(
                      children: [
                        PersonaAvatar(
                          assetId: person['avatar_asset_id'] as String?,
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Text(
                            person['display_name'] as String,
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (person['status'] == 'resetting')
                      const Text('资料正在清除，请在设置中查看进度。'),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        FilledButton(
                          onPressed: person['status'] == 'resetting'
                              ? null
                              : () => context.push(
                                  '/personas/${person['id']}/chat',
                                ),
                          child: const Text('继续聊天'),
                        ),
                        OutlinedButton(
                          onPressed: person['status'] == 'resetting'
                              ? null
                              : () => context.push(
                                  '/personas/${person['id']}/history',
                                ),
                          child: const Text('历史对话'),
                        ),
                        TextButton(
                          onPressed: person['status'] == 'resetting'
                              ? null
                              : () async {
                                  await context.push(
                                    '/personas/${person['id']}/edit',
                                  );
                                  reload();
                                },
                          child: const Text('编辑人物'),
                        ),
                        TextButton(
                          onPressed: person['status'] == 'resetting'
                              ? null
                              : () => context.push(
                                  '/personas/${person['id']}/memories',
                                ),
                          child: const Text('管理记忆'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () async {
                  await context.push('/personas/new');
                  if (context.mounted) context.go('/');
                },
                icon: const Icon(Icons.add),
                label: const Text('建立 AI 陪伴人物'),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

class ConversationHistoryPage extends StatelessWidget {
  const ConversationHistoryPage({required this.personaId, super.key});
  final String personaId;
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('历史对话')),
    body: ResourceList(
      path: '/conversations',
      query: {'persona_id': personaId},
      emptyText: '还没有对话。',
      itemBuilder: (context, conversation, reload) {
        final raw = DateTime.tryParse(
          conversation['created_at']?.toString() ?? '',
        )?.toLocal();
        final label = raw == null
            ? '对话'
            : '${raw.year}年${raw.month}月${raw.day}日 ${raw.hour}:${raw.minute.toString().padLeft(2, '0')}';
        return Card(
          child: ListTile(
            title: Text(label),
            subtitle: const Text('查看与继续聊天'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.push(
              '/personas/$personaId/chat?conversation=${conversation['id']}',
            ),
          ),
        );
      },
    ),
    bottomNavigationBar: SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: FilledButton(
          onPressed: () => context.push('/personas/$personaId/chat?new=1'),
          child: const Text('开启新对话'),
        ),
      ),
    ),
  );
}
