import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/providers.dart';
import '../../app/widgets.dart';
import '../../core/network/api.dart';

String memoryLabel(String status) => switch (status) {
  'candidate' => '待您确认',
  'indexing' => '记忆准备中',
  'active' => '已确认并可使用',
  'rejected' => '已拒绝',
  'superseded' => '已被新版本替代',
  _ => status,
};

class MemoriesPage extends ConsumerStatefulWidget {
  const MemoriesPage({required this.personaId, super.key});
  final String personaId;
  @override
  ConsumerState<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends ConsumerState<MemoriesPage> {
  String _filter = 'candidate';
  String? _busyId;
  String? _error;
  Future<void> _act(Json memory, String action, VoidCallback reload) async {
    if (_busyId != null) return;
    String? content;
    if (action == 'delete') {
      if (!await confirmAction(
        context,
        '从长期记忆中移除？',
        '此后不会把这条资料作为长期记忆使用。原聊天仍保留，也可能出现在近期上下文中。需要清除原始聊天时，请到设置中清除该人物全部对话与记忆。',
        '移除记忆',
      )) {
        return;
      }
    }
    if (!mounted) return;
    if (action == 'edit') {
      final controller = TextEditingController(
        text: memory['content'] as String,
      );
      content = await showDialog<String>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('编辑记忆'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: controller,
                  minLines: 3,
                  maxLines: 6,
                  maxLength: 500,
                  decoration: const InputDecoration(labelText: '准确的资料'),
                ),
                const Text('保存后会清除旧向量，需要重新确认，准备完成后才用于聊天。'),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () {
                if (controller.text.trim().isNotEmpty) {
                  Navigator.pop(context, controller.text.trim());
                }
              },
              child: const Text('保存修改'),
            ),
          ],
        ),
      );
      // The dialog route may still animate with the field mounted; dispose after
      // its transition finishes rather than invalidating a live controller.
      Future<void>.delayed(
        const Duration(milliseconds: 350),
        controller.dispose,
      );
      if (content == null) return;
    }
    if (!mounted) return;
    setState(() {
      _busyId = memory['id'] as String;
      _error = null;
    });
    try {
      final api = ref.read(apiProvider);
      final path = '/memories/${memory['id']}';
      if (action == 'delete') {
        await api.delete(path);
      } else if (action == 'edit') {
        await api.patch(path, {
          'revision': memory['revision'],
          'content': content,
        });
      } else {
        await api.post('$path/$action', {'revision': memory['revision']});
      }
      reload();
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busyId = null);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('您来决定，记住什么')),
    body: Column(
      children: [
        const Padding(
          padding: EdgeInsets.all(20),
          child: Text('只有您确认并准备完成的资料，才会作为长期记忆使用。请把不准确的内容改正或拒绝。'),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: DropdownButtonFormField<String>(
            initialValue: _filter,
            decoration: const InputDecoration(labelText: '查看范围'),
            isExpanded: true,
            items: const [
              DropdownMenuItem(value: 'candidate', child: Text('待确认')),
              DropdownMenuItem(value: 'active', child: Text('已确认可使用')),
              DropdownMenuItem(value: 'indexing', child: Text('准备中')),
              DropdownMenuItem(value: '', child: Text('全部记忆')),
            ],
            onChanged: (value) => setState(() => _filter = value!),
          ),
        ),
        if (_error != null) ErrorNotice(_error!),
        Expanded(
          child: ResourceList(
            key: ValueKey(_filter),
            path: '/memories',
            query: {
              'persona_id': widget.personaId,
              if (_filter.isNotEmpty) 'status': _filter,
            },
            emptyText: '这里还没有记忆。聊天后，您可以在这里确认需要记住的资料。',
            itemBuilder: (context, memory, reload) => Card(
              margin: const EdgeInsets.only(bottom: 16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      memoryLabel(memory['status'] as String),
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                    const SizedBox(height: 10),
                    SelectableText(memory['content'] as String),
                    if (memory['source_message_ids'] is List &&
                        (memory['source_message_ids'] as List).isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(
                          '来源：您曾发送的 ${(memory['source_message_ids'] as List).length} 条消息',
                        ),
                      ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        if (memory['status'] == 'candidate') ...[
                          FilledButton(
                            onPressed: _busyId == null
                                ? () => _act(memory, 'confirm', reload)
                                : null,
                            child: const Text('确认记住'),
                          ),
                          OutlinedButton(
                            onPressed: _busyId == null
                                ? () => _act(memory, 'reject', reload)
                                : null,
                            child: const Text('不准确，拒绝'),
                          ),
                        ],
                        if (memory['status'] != 'rejected' &&
                            memory['status'] != 'superseded')
                          TextButton(
                            onPressed: _busyId == null
                                ? () => _act(memory, 'edit', reload)
                                : null,
                            child: const Text('编辑'),
                          ),
                        TextButton(
                          onPressed: _busyId == null
                              ? () => _act(memory, 'delete', reload)
                              : null,
                          child: const Text('从长期记忆中移除'),
                        ),
                      ],
                    ),
                    if (_busyId == memory['id'])
                      const LinearProgressIndicator(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}
