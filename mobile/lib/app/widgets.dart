import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/network/api.dart';
import 'providers.dart';

class IdentityNotice extends StatelessWidget {
  const IdentityNotice({super.key});
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.secondaryContainer,
      borderRadius: BorderRadius.circular(16),
    ),
    child: const Text('这是 AI 陪伴助手。它参考您设定的表达习惯，不是真实亲属。'),
  );
}

class ErrorNotice extends StatelessWidget {
  const ErrorNotice(this.message, {this.retry, super.key});
  final String message;
  final VoidCallback? retry;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(12),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          message,
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
        if (retry != null)
          TextButton(onPressed: retry, child: const Text('重新加载')),
      ],
    ),
  );
}

Future<bool> confirmAction(
  BuildContext context,
  String title,
  String explanation,
  String action,
) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(explanation),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('暂不'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(action),
          ),
        ],
      ),
    ) ??
    false;

class PersonaAvatar extends ConsumerStatefulWidget {
  const PersonaAvatar({this.assetId, this.radius = 30, super.key});
  final String? assetId;
  final double radius;
  @override
  ConsumerState<PersonaAvatar> createState() => _PersonaAvatarState();
}

class _PersonaAvatarState extends ConsumerState<PersonaAvatar> {
  Future<String?>? _url;
  var _retried = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(PersonaAvatar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.assetId != widget.assetId) {
      _retried = false;
      _load();
    }
  }

  void _load() {
    _url = widget.assetId == null
        ? Future.value(null)
        : () async {
            final api = ref.read(apiProvider);
            final result = await api.get('/assets/${widget.assetId}/read-url');
            return Uri.parse(
              api.dio.options.baseUrl,
            ).resolve(result['url'] as String).toString();
          }();
  }

  Widget placeholder() =>
      Icon(Icons.person_rounded, size: widget.radius, semanticLabel: '人物头像');
  @override
  Widget build(BuildContext context) => CircleAvatar(
    radius: widget.radius,
    child: ClipOval(
      child: FutureBuilder<String?>(
        future: _url,
        builder: (context, snapshot) {
          if (!snapshot.hasData) return placeholder();
          return Image.network(
            snapshot.data!,
            width: widget.radius * 2,
            height: widget.radius * 2,
            fit: BoxFit.cover,
            semanticLabel: '人物头像',
            errorBuilder: (context, _, stack) {
              if (!_retried) {
                _retried = true;
                Future.microtask(() {
                  if (mounted) setState(_load);
                });
              }
              return placeholder();
            },
          );
        },
      ),
    ),
  );
}

/// A cursor-aware list with explicit loading/retry controls for large text users.
class ResourceList extends ConsumerStatefulWidget {
  const ResourceList({
    required this.path,
    required this.itemBuilder,
    this.query = const {},
    this.emptyText = '这里还没有内容。',
    super.key,
  });
  final String path;
  final Json query;
  final Widget Function(BuildContext, Json, VoidCallback reload) itemBuilder;
  final String emptyText;
  @override
  ConsumerState<ResourceList> createState() => _ResourceListState();
}

class _ResourceListState extends ConsumerState<ResourceList> {
  final _items = <Json>[];
  String? _next;
  String? _error;
  bool _loading = true;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool more = false}) async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await ref
          .read(apiProvider)
          .get(
            widget.path,
            query: {
              ...widget.query,
              'limit': 30,
              if (more && _next != null) 'cursor': _next,
            },
          );
      if (!mounted) return;
      setState(() {
        if (!more) _items.clear();
        _items.addAll((page['items'] as List).cast<Json>());
        _next = page['next_cursor']?.toString();
      });
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: _load,
    child: ListView(
      padding: const EdgeInsets.all(20),
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        if (_items.isEmpty && !_loading && _error == null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 40),
            child: Text(widget.emptyText),
          ),
        ..._items.map((item) => widget.itemBuilder(context, item, _load)),
        if (_error != null)
          ErrorNotice(_error!, retry: () => _load(more: _items.isNotEmpty)),
        if (_loading)
          const Center(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: CircularProgressIndicator(),
            ),
          ),
        if (_next != null && !_loading)
          OutlinedButton(
            onPressed: () => _load(more: true),
            child: const Text('加载更多'),
          ),
      ],
    ),
  );
}
