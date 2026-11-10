import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:uuid/uuid.dart';

import '../../app/providers.dart';
import '../../app/widgets.dart';
import '../../core/network/api.dart';
import '../../core/network/sse.dart';

class PersonaEditorPage extends ConsumerStatefulWidget {
  const PersonaEditorPage({this.personaId, super.key});
  final String? personaId;
  @override
  ConsumerState<PersonaEditorPage> createState() => _PersonaEditorPageState();
}

class _PersonaEditorPageState extends ConsumerState<PersonaEditorPage> {
  final _name = TextEditingController(text: '小雨 AI 陪伴');
  final _reference = TextEditingController();
  final _address = TextEditingController(text: '您');
  final _phrases = TextEditingController(text: '您慢慢说');
  final _avoided = TextEditingController(text: '你必须');
  final _examples = TextEditingController();
  int _step = 0;
  int _styleVersion = 1;
  String _warmth = 'high';
  String _length = 'short';
  String _humor = 'light';
  String? _assetId;
  XFile? _photo;
  bool _authorized = false;
  bool _busy = false;
  String? _error;
  @override
  void initState() {
    super.initState();
    _initialize();
  }

  Future<void> _initialize() async {
    if (widget.personaId != null) {
      setState(() => _busy = true);
      try {
        final person = await ref
            .read(apiProvider)
            .get('/personas/${widget.personaId}');
        if (!mounted) return;
        final style = person['style'] as Json;
        setState(() {
          _name.text = person['display_name'] as String;
          _reference.text = person['relationship_reference'] as String? ?? '';
          _address.text = style['address_user'] as String? ?? '您';
          _warmth = style['warmth'] as String? ?? 'high';
          _length = style['sentence_length'] as String? ?? 'short';
          _humor = style['humor'] as String? ?? 'light';
          _phrases.text = ((style['preferred_phrases'] ?? []) as List).join(
            '\n',
          );
          _avoided.text = ((style['avoided_phrases'] ?? []) as List).join('\n');
          _examples.text = ((person['examples'] ?? []) as List)
              .map((e) => e is Map ? e['content'] : e)
              .join('\n');
          _styleVersion = person['style_version'] as int;
          _assetId = person['avatar_asset_id'] as String?;
          _authorized = true;
        });
      } catch (e) {
        if (mounted) setState(() => _error = errorMessage(e));
      }
      if (mounted) setState(() => _busy = false);
    }
    try {
      final lost = await ImagePicker().retrieveLostData();
      if (lost.files?.isNotEmpty == true && mounted) {
        setState(() => _photo = lost.files!.first);
      }
    } catch (_) {
      /* A missing interrupted photo can be selected again. */
    }
  }

  @override
  void dispose() {
    for (final controller in [
      _name,
      _reference,
      _address,
      _phrases,
      _avoided,
      _examples,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  List<String> _lines(TextEditingController c) => c.text
      .split('\n')
      .map((s) => s.trim())
      .where((s) => s.isNotEmpty)
      .toList();
  Future<void> _pick() async {
    try {
      final image = await ImagePicker().pickImage(
        source: ImageSource.gallery,
        maxWidth: 1600,
      );
      if (image == null) return;
      if (await image.length() > 5 * 1024 * 1024) {
        throw StateError('照片请控制在 5 MB 以内。');
      }
      if (mounted) {
        setState(() {
          _photo = image;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
  }

  bool _validate() {
    String? error;
    if (_name.text.trim().isEmpty || _name.text.trim().length > 40) {
      error = '人物名称请填写 1 至 40 个字。';
    } else if (_address.text.trim().isEmpty) {
      error = '请填写希望 AI 如何称呼您。';
    } else if (_lines(_examples).length > 30 ||
        _lines(_examples).any((e) => e.length > 500)) {
      error = '例句最多 30 条，每条不超过 500 字。';
    } else if ([_phrases, _avoided].any(
      (c) => _lines(c).length > 10 || _lines(c).any((s) => s.length > 100),
    )) {
      error = '喜欢和避免的说法各最多 10 条，每条不超过 100 字。';
    } else if (!_authorized) {
      error = '请确认您有权使用照片和例句。';
    }
    setState(() => _error = error);
    return error == null;
  }

  Future<void> _save({bool preview = false}) async {
    if (!_validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiProvider);
      if (_photo != null) {
        final upload = await api.post(
          '/assets/avatar',
          FormData.fromMap({
            'file': await MultipartFile.fromFile(
              _photo!.path,
              filename: _photo!.name,
            ),
          }),
        );
        _assetId = upload['asset_id'] as String;
        _photo = null;
      }
      final body = <String, dynamic>{
        'display_name': _name.text.trim(),
        'avatar_asset_id': _assetId,
        'relationship_reference': _reference.text.trim(),
        'style': {
          'address_user': _address.text.trim(),
          'sentence_length': _length,
          'warmth': _warmth,
          'humor': _humor,
          'preferred_phrases': _lines(_phrases),
          'avoided_phrases': _lines(_avoided),
        },
        'examples': _lines(_examples),
        if (widget.personaId != null) 'style_version': _styleVersion,
      };
      final result = widget.personaId == null
          ? await api.post('/personas', body)
          : await api.patch('/personas/${widget.personaId}', body);
      if (!mounted) return;
      ref.read(personasRevisionProvider.notifier).state++;
      if (preview) {
        context.pushReplacement('/personas/${result['id']}/preview');
      } else {
        context.pop();
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busy = false);
  }

  Widget _field(
    TextEditingController c,
    String label, {
    int lines = 1,
    int? maxLength,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: TextField(
      controller: c,
      maxLines: lines,
      maxLength: maxLength,
      decoration: InputDecoration(labelText: label),
      enabled: !_busy,
    ),
  );
  Widget _options(
    String title,
    String value,
    Map<String, String> options,
    void Function(String) update,
  ) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: DropdownButtonFormField<String>(
      initialValue: options.containsKey(value) ? value : options.keys.first,
      isExpanded: true,
      decoration: InputDecoration(labelText: title),
      items: options.entries
          .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
          .toList(),
      onChanged: _busy ? null : (value) => setState(() => update(value!)),
    ),
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(widget.personaId == null ? '建立 AI 陪伴人物' : '编辑表达习惯'),
    ),
    body: Column(
      children: [
        if (_error != null)
          ErrorNotice(
            _error!,
            retry: widget.personaId == null || _busy ? null : _initialize,
          ),
        if (_busy) const LinearProgressIndicator(),
        Expanded(
          child: Stepper(
            currentStep: _step,
            onStepTapped: _busy ? null : (step) => setState(() => _step = step),
            controlsBuilder: (context, details) => Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  if (_step < 2)
                    FilledButton(
                      onPressed: _busy ? null : () => setState(() => _step++),
                      child: const Text('下一步'),
                    ),
                  if (_step == 2) ...[
                    FilledButton(
                      onPressed: _busy ? null : _save,
                      child: const Text('保存人物'),
                    ),
                    OutlinedButton(
                      onPressed: _busy ? null : () => _save(preview: true),
                      child: const Text('保存并试聊'),
                    ),
                  ],
                  if (_step > 0)
                    TextButton(
                      onPressed: _busy ? null : () => setState(() => _step--),
                      child: const Text('上一步'),
                    ),
                ],
              ),
            ),
            steps: [
              Step(
                title: const Text('照片与名称'),
                isActive: _step >= 0,
                content: Column(
                  children: [
                    const IdentityNotice(),
                    const SizedBox(height: 16),
                    if (_photo != null)
                      ClipOval(
                        child: Image.file(
                          File(_photo!.path),
                          width: 100,
                          height: 100,
                          fit: BoxFit.cover,
                        ),
                      )
                    else
                      PersonaAvatar(assetId: _assetId, radius: 50),
                    TextButton.icon(
                      onPressed: _busy ? null : _pick,
                      icon: const Icon(Icons.photo_library_outlined),
                      label: const Text('从相册选择照片'),
                    ),
                    if (_photo != null || _assetId != null)
                      TextButton(
                        onPressed: _busy
                            ? null
                            : () => setState(() {
                                _photo = null;
                                _assetId = null;
                              }),
                        child: const Text('移除头像'),
                      ),
                    const Text('照片仅用于头像展示，不用于推断性格。'),
                    const SizedBox(height: 16),
                    _field(_name, '人物名称', maxLength: 40),
                    _field(_reference, '表达风格参考（选填）', maxLength: 200),
                  ],
                ),
              ),
              Step(
                title: const Text('表达习惯'),
                isActive: _step >= 1,
                content: Column(
                  children: [
                    _field(_address, '希望如何称呼您', maxLength: 40),
                    _options('句子长短', _length, {
                      'short': '简短',
                      'medium': '适中',
                    }, (v) => _length = v),
                    _options('表达温度', _warmth, {
                      'high': '亲切温和',
                      'medium': '自然平和',
                      'low': '克制简洁',
                    }, (v) => _warmth = v),
                    _options('幽默程度', _humor, {
                      'none': '不加玩笑',
                      'light': '偶尔轻松一点',
                    }, (v) => _humor = v),
                    _field(_phrases, '喜欢的说法（每行一条）', lines: 3, maxLength: 1000),
                    _field(
                      _avoided,
                      '希望避免的说法（每行一条）',
                      lines: 3,
                      maxLength: 1000,
                    ),
                  ],
                ),
              ),
              Step(
                title: const Text('例句与试聊'),
                isActive: _step >= 2,
                content: Column(
                  children: [
                    const Text('例句只用来参考说话方式，不会当作真实经历。每行一条，可先留空。'),
                    const SizedBox(height: 16),
                    _field(_examples, '已授权的例句', lines: 5, maxLength: 15000),
                    CheckboxListTile(
                      value: _authorized,
                      contentPadding: EdgeInsets.zero,
                      onChanged: _busy
                          ? null
                          : (v) => setState(() => _authorized = v ?? false),
                      title: const Text('我有权使用这些照片和例句，并确认例句内容。'),
                    ),
                    const Text('试聊不会保存长期记忆，也不会通知现实联系人。'),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

class PreviewPage extends ConsumerStatefulWidget {
  const PreviewPage({required this.personaId, super.key});
  final String personaId;
  @override
  ConsumerState<PreviewPage> createState() => _PreviewPageState();
}

class _PreviewPageState extends ConsumerState<PreviewPage> {
  final _question = TextEditingController(text: '我今天有点想念以前的生活。');
  String? _reply, _error, _id, _sentQuestion, _runId;
  bool _busy = false;
  @override
  void dispose() {
    _question.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    if (_question.text.trim().isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    if (_sentQuestion != _question.text) {
      _id = null;
      _runId = null;
    }
    _sentQuestion = _question.text;
    _id ??= const Uuid().v4();
    try {
      final api = ref.read(apiProvider);
      if (_runId == null) {
        final result = await api.post('/personas/${widget.personaId}/preview', {
          'client_message_id': _id,
          'sample_question': _sentQuestion,
        });
        _runId = result['run_id'] as String;
      }
      for (var i = 0; i < 40 && mounted; i++) {
        final snapshot = await api.get('/runs/$_runId');
        if (isRunTerminal(snapshot['status'] as String)) {
          if (snapshot['status'] != 'completed') {
            throw StateError('这次试聊未完成，请换个问题再试。');
          }
          if (mounted) {
            setState(
              () => _reply = snapshot['assistant_message']['content'] as String,
            );
          }
          _id = null;
          _runId = null;
          break;
        }
        await Future<void>.delayed(const Duration(seconds: 2));
      }
      if (mounted && _runId != null) {
        setState(() => _error = '回复还在准备，点“查看回复”继续查看。');
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('表达方式试聊')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const IdentityNotice(),
        const SizedBox(height: 12),
        const Text('试聊不使用或新增私人长期记忆，不会通知现实联系人。'),
        const SizedBox(height: 20),
        TextField(
          controller: _question,
          maxLines: 4,
          maxLength: 2000,
          enabled: !_busy,
          decoration: const InputDecoration(labelText: '想试问的问题'),
        ),
        FilledButton(
          onPressed: _busy ? null : _send,
          child: Text(_runId == null ? '试一试' : '查看回复'),
        ),
        if (_busy)
          const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
        if (_reply != null)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: SelectableText(_reply!),
            ),
          ),
        if (_error != null) ErrorNotice(_error!),
        OutlinedButton(
          onPressed: () => context.go('/'),
          child: const Text('回到人物列表'),
        ),
      ],
    ),
  );
}
