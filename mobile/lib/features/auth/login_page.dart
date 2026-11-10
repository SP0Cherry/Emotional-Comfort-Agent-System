import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/providers.dart';
import '../../app/widgets.dart';
import '../../core/network/api.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});
  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  String? _challenge;
  String? _challengedPhone;
  String? _developmentCode;
  String? _error;
  bool _busy = false;
  bool _consent = false;
  @override
  void dispose() {
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _request() async {
    if (!RegExp(r'^1\d{10}$').hasMatch(_phone.text.trim())) {
      setState(() => _error = '请填写 11 位中国大陆手机号。');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final phone = _phone.text.trim();
      final result = await ref.read(apiProvider).publicPost(
        '/auth/otp/request',
        {'phone': phone},
      );
      if (mounted) {
        setState(() {
          _challenge = result['challenge_id'] as String;
          _challengedPhone = phone;
          _developmentCode =
              (result['development_code'] ?? result['dev_code']) as String?;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _verify() async {
    if (_challengedPhone != _phone.text.trim()) {
      setState(() => _error = '手机号已变更，请重新获取验证码。');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiProvider);
      final tokens = await api.publicPost('/auth/otp/verify', {
        'phone': _challengedPhone,
        'code': _code.text.trim(),
        'challenge_id': _challenge,
      });
      await api.acceptTokens(tokens);
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: ListView(
            padding: const EdgeInsets.all(28),
            shrinkWrap: true,
            children: [
              const Icon(
                Icons.spa_outlined,
                size: 64,
                color: Color(0xff406a56),
              ),
              const SizedBox(height: 20),
              Text(
                '慢慢说，我听着',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 12),
              const IdentityNotice(),
              const SizedBox(height: 24),
              TextField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                maxLength: 11,
                autofillHints: const [AutofillHints.telephoneNumberNational],
                decoration: const InputDecoration(
                  labelText: '手机号',
                  hintText: '用于登录您的账户',
                ),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: _busy || !_consent ? null : _request,
                child: Text(_challenge == null ? '获取验证码' : '重新获取验证码'),
              ),
              if (_developmentCode != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text('开发环境验证码：$_developmentCode'),
                ),
              if (_challenge != null) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _code,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  autofillHints: const [AutofillHints.oneTimeCode],
                  decoration: const InputDecoration(labelText: '短信验证码'),
                ),
                FilledButton(
                  onPressed: _busy || !_consent ? null : _verify,
                  child: const Text('登录并开始'),
                ),
              ],
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _consent,
                onChanged: _busy
                    ? null
                    : (value) => setState(() => _consent = value ?? false),
                title: const Text('我了解：聊天内容和照片会提交到本项目服务，AI 回复可能不准确。'),
                subtitle: const Text('请勿把本应用作为紧急求助渠道。此版本用于开发和小范围验证。'),
              ),
              if (_busy) const Center(child: CircularProgressIndicator()),
              if (_error != null) ErrorNotice(_error!),
            ],
          ),
        ),
      ),
    ),
  );
}
