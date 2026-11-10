import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/providers.dart';
import '../../app/widgets.dart';
import '../../core/network/api.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});
  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  static const _exportChannel = MethodChannel('companion/export');
  List<Json> _personas = [];
  final _operations = <String, Json>{};
  String? _error;
  String? _busy;
  bool _loading = true;
  Timer? _poll;
  bool _polling = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final people = await ref
          .read(apiProvider)
          .list('/personas', query: {'limit': 30});
      if (!mounted) return;
      setState(() {
        _personas = people;
        _error = null;
        _loading = false;
      });
      final prefs = ref.read(localStoreProvider).preferences;
      for (final person in people) {
        final id = person['id'] as String;
        final operationId = person['status'] == 'resetting'
            ? (person['reset_operation_id'] as String? ??
                  prefs.getString('operation:$id'))
            : prefs.getString('operation:$id');
        if (operationId != null) {
          _operations.putIfAbsent(
            id,
            () => {'job_id': operationId, 'status': 'pending'},
          );
        }
      }
      _startPoll();
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = errorMessage(e);
          _loading = false;
        });
      }
    }
  }

  void _startPoll() {
    _poll ??= Timer.periodic(
      const Duration(seconds: 3),
      (_) => _pollOperations(),
    );
    unawaited(_pollOperations());
  }

  Future<void> _pollOperations() async {
    if (_polling || !mounted) return;
    _polling = true;
    try {
      for (final personaId in _operations.keys.toList()) {
        final operation = _operations[personaId]!;
        if (const {
          'completed',
          'succeeded',
          'failed',
        }.contains(operation['status'])) {
          continue;
        }
        try {
          final result = await ref
              .read(apiProvider)
              .get('/operations/${operation['job_id']}');
          if (!mounted) return;
          _operations[personaId] = {...result, 'job_id': operation['job_id']};
          if (const {'completed', 'succeeded'}.contains(result['status'])) {
            await ref
                .read(localStoreProvider)
                .preferences
                .remove('operation:$personaId');
            await ref.read(localStoreProvider).clearRecovery(personaId);
            ref.invalidate(chatProvider(personaId));
            _personas = await ref
                .read(apiProvider)
                .list('/personas', query: {'limit': 30});
            ref.read(personasRevisionProvider.notifier).state++;
          }
          if (mounted) setState(() {});
        } catch (e) {
          if (mounted) setState(() => _error = errorMessage(e));
        }
      }
    } finally {
      _polling = false;
    }
  }

  Future<void> _reset(Json person) async {
    if (!await confirmAction(
      context,
      '清除全部对话与记忆？',
      '将清除“${person['display_name']}”的全部原始聊天和长期记忆，停止相关生成任务。清理完成前暂停使用这个人物。此操作不能撤回。',
      '确认清除',
    )) {
      return;
    }
    if (!mounted) return;
    setState(() {
      _busy = person['id'] as String;
      _error = null;
    });
    try {
      final result = await ref.read(apiProvider).post(
        '/personas/${person['id']}/reset-context',
        {'confirm': true},
      );
      final id = person['id'] as String;
      final jobId = (result['job_id'] ?? result['operation_id']) as String;
      await ref
          .read(localStoreProvider)
          .preferences
          .setString('operation:$id', jobId);
      if (!mounted) return;
      setState(() {
        person['status'] = 'resetting';
        _operations[id] = {'job_id': jobId, 'status': 'pending'};
      });
      ref.read(personasRevisionProvider.notifier).state++;
      _startPoll();
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busy = null);
  }

  Future<void> _export(Json person) async {
    if (!await confirmAction(
      context,
      '导出人物资料？',
      '导出文件包含个人资料、聊天和记忆。请保存到您信任的位置，并妥善保管。',
      '选择保存位置',
    )) {
      return;
    }
    if (!mounted) return;
    setState(() {
      _busy = person['id'] as String;
      _error = null;
    });
    try {
      final data = await ref
          .read(apiProvider)
          .get('/personas/${person['id']}/export');
      final saved = await _exportChannel.invokeMethod<bool>('saveJson', {
        'filename': 'companion-${person['id']}.json',
        'content': const JsonEncoder.withIndent('  ').convert(data),
      });
      if (mounted && saved == true) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('资料已保存到您选择的位置。')));
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busy = null);
  }

  Future<void> _logout() async {
    setState(() {
      _busy = 'logout';
      _error = null;
    });
    try {
      await ref.read(apiProvider).logout();
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busy = null);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('设置与资料')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('大字号'),
          subtitle: const Text('同时尊重手机系统的文字大小设置。'),
          value: ref.watch(largeTextProvider),
          onChanged: (value) {
            ref.read(largeTextProvider.notifier).state = value;
            unawaited(ref.read(localStoreProvider).setLargeText(value));
          },
        ),
        const SizedBox(height: 16),
        const IdentityNotice(),
        const SizedBox(height: 20),
        const Text('聊天正文与草稿不永久缓存在手机。退出账户会清除本机令牌和恢复标记；服务器上的资料可按人物清除。'),
        if (_loading) const LinearProgressIndicator(),
        if (_error != null) ErrorNotice(_error!, retry: _load),
        ..._personas.map((person) {
          final operation = _operations[person['id']];
          final resetting = person['status'] == 'resetting';
          return Card(
            margin: const EdgeInsets.symmetric(vertical: 12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    person['display_name'] as String,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  if (operation != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      child: Text(
                        operation['status'] == 'failed'
                            ? '清理未完成。人物已暂停，请联系项目管理员。错误：${operation['error_code'] ?? '未知'}'
                            : const {
                                'completed',
                                'succeeded',
                              }.contains(operation['status'])
                            ? '全部对话与记忆已清除。'
                            : '正在清除资料，请稍等……',
                      ),
                    ),
                  if (resetting && operation == null)
                    const Text('正在清除资料。可稍后刷新；如持续未完成，请联系项目管理员。'),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      OutlinedButton(
                        onPressed: _busy != null || resetting
                            ? null
                            : () => _export(person),
                        child: const Text('导出资料'),
                      ),
                      TextButton(
                        onPressed: _busy != null || resetting
                            ? null
                            : () => _reset(person),
                        child: const Text('清除全部对话与记忆'),
                      ),
                    ],
                  ),
                  if (_busy == person['id']) const LinearProgressIndicator(),
                ],
              ),
            ),
          );
        }),
        const SizedBox(height: 20),
        OutlinedButton(
          onPressed: _busy != null ? null : _logout,
          child: const Text('退出登录'),
        ),
        const SizedBox(height: 16),
        const Text('AI 陪伴 · 开发验证版 0.1\n如果遇到现实困难，请联系身边可信任的人。'),
      ],
    ),
  );
}
