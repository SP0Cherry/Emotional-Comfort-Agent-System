import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../storage/local_store.dart';
import 'sse.dart';

typedef Json = Map<String, dynamic>;

class Api extends ChangeNotifier {
  Api(this.store, {Dio? transport})
    : dio =
          transport ??
          Dio(
            BaseOptions(
              baseUrl: const String.fromEnvironment(
                'API_BASE_URL',
                defaultValue: 'http://10.0.2.2:8000',
              ),
              connectTimeout: const Duration(seconds: 12),
              receiveTimeout: const Duration(seconds: 30),
            ),
          ) {
    if (kReleaseMode && Uri.parse(dio.options.baseUrl).scheme != 'https') {
      throw StateError('正式版本必须通过 API_BASE_URL 配置 HTTPS 服务地址。');
    }
  }
  final LocalStore store;
  final Dio dio;
  String? accessToken;
  String? refreshToken;
  Future<void>? _refreshing;
  int _sessionGeneration = 0;
  bool get signedIn => refreshToken != null;

  Future<void> restore() async {
    final saved = await store.tokens();
    accessToken = saved?['access_token'] as String?;
    refreshToken = saved?['refresh_token'] as String?;
  }

  Future<void> acceptTokens(Json tokens) async {
    accessToken = tokens['access_token'] as String;
    refreshToken = tokens['refresh_token'] as String;
    await store.saveTokens(accessToken!, refreshToken!);
    notifyListeners();
  }

  Future<void> _refresh() {
    if (_refreshing != null) return _refreshing!;
    final generation = _sessionGeneration;
    final token = refreshToken;
    final future = () async {
      if (token == null) throw StateError('请重新登录。');
      try {
        final response = await dio.post<Json>(
          '/v1/auth/refresh',
          data: {'refresh_token': token},
        );
        if (generation != _sessionGeneration) throw StateError('登录状态已变更。');
        await acceptTokens(response.data!);
      } on DioException catch (error) {
        if (error.response?.statusCode == 401 ||
            error.response?.statusCode == 403) {
          await clearSession();
        }
        rethrow;
      }
    }();
    _refreshing = future;
    return future.whenComplete(() => _refreshing = null);
  }

  Future<Response<T>> request<T>(
    String path, {
    String method = 'GET',
    dynamic data,
    Json? query,
    bool authenticated = true,
    ResponseType? responseType,
    CancelToken? cancelToken,
  }) async {
    final sentToken = accessToken;
    Future<Response<T>> send() => dio.request<T>(
      path.startsWith('/v1/') ? path : '/v1$path',
      data: data,
      queryParameters: query,
      cancelToken: cancelToken,
      options: Options(
        method: method,
        responseType: responseType,
        receiveTimeout: responseType == ResponseType.stream
            ? const Duration(seconds: 40)
            : null,
        headers: authenticated
            ? {'Authorization': 'Bearer $accessToken'}
            : null,
      ),
    );
    try {
      return await send();
    } on DioException catch (error) {
      if (!authenticated ||
          error.response?.statusCode != 401 ||
          refreshToken == null) {
        rethrow;
      }
      if (sentToken == accessToken) await _refresh();
      return send(); // At most one retry. POST idempotency ID is preserved in data.
    }
  }

  Future<Json> get(String path, {Json? query}) async =>
      (await request<Json>(path, query: query)).data!;
  Future<Json> post(String path, [dynamic data]) async =>
      (await request<Json>(path, method: 'POST', data: data)).data ?? {};
  Future<Json> patch(String path, Json data) async =>
      (await request<Json>(path, method: 'PATCH', data: data)).data!;
  Future<void> delete(String path) async =>
      request<dynamic>(path, method: 'DELETE');
  Future<Json> publicPost(String path, Json data) async => (await request<Json>(
    path,
    method: 'POST',
    data: data,
    authenticated: false,
  )).data!;
  Future<List<Json>> list(String path, {Json? query}) async =>
      ((await get(path, query: query))['items'] as List).cast<Json>();

  Stream<ServerEvent> events(
    String runId,
    int afterSeq,
    CancelToken cancelToken,
  ) async* {
    final response = await request<ResponseBody>(
      '/runs/$runId/events',
      query: {'after_seq': afterSeq},
      responseType: ResponseType.stream,
      cancelToken: cancelToken,
    );
    yield* parseServerEvents(response.data!.stream);
  }

  Future<void> logout() async {
    final token = refreshToken;
    if (token != null) await post('/auth/logout', {'refresh_token': token});
    await clearSession();
  }

  Future<void> clearSession() async {
    _sessionGeneration++;
    accessToken = null;
    refreshToken = null;
    await store.clearSession();
    notifyListeners();
  }
}

String errorMessage(Object error) {
  if (error is DioException) {
    final body = error.response?.data;
    if (body is Map && body['error'] is Map) {
      return body['error']['message']?.toString() ?? '操作未完成，请稍后重试。';
    }
    if (error.response?.statusCode == 429) return '操作较频繁，请稍等一会儿。';
    if (error.response?.statusCode == 401) return '登录已过期，请重新登录。';
    if (error.type == DioExceptionType.connectionError ||
        error.type == DioExceptionType.connectionTimeout) {
      return '暂时连不上服务，请检查网络后重试。';
    }
    return '操作未完成，请稍后重试。';
  }
  return error is StateError ? error.message.toString() : '操作未完成，请稍后重试。';
}
