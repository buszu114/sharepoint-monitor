import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

void main() => runApp(const MonitorApp());

class MonitorApp extends StatelessWidget {
  const MonitorApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Monitor SharePoint', debugShowCheckedModeBanner: false,
    theme: ThemeData(colorSchemeSeed: const Color(0xff1765b3), useMaterial3: true),
    home: const HomePage(),
  );
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final storage = const FlutterSecureStorage();
  final endpoint = TextEditingController();
  final apiKey = TextEditingController();
  List<dynamic> changes = [];
  Map<String, dynamic> status = {};
  String message = 'Ustaw adres serwera i klucz API.';
  bool loading = false;

  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    endpoint.text = await storage.read(key: 'endpoint') ?? '';
    apiKey.text = await storage.read(key: 'apiKey') ?? '';
    if (endpoint.text.isNotEmpty && apiKey.text.isNotEmpty) await refresh();
  }
  Uri get base => Uri.parse(endpoint.text.trim());
  Future<dynamic> request(String path, {bool post = false}) async {
    if (base.scheme != 'https') throw Exception('Serwer musi używać HTTPS.');
    final uri = base.resolve(path);
    final headers = {'X-API-Key': apiKey.text.trim()};
    final res = post ? await http.post(uri, headers: headers) : await http.get(uri, headers: headers);
    if (res.statusCode != 200) throw Exception('HTTP ${res.statusCode}: ${res.body}');
    return jsonDecode(utf8.decode(res.bodyBytes));
  }
  Future<void> refresh({bool scan = false}) async {
    setState(() { loading = true; message = 'Ładowanie...'; });
    try {
      await storage.write(key: 'endpoint', value: endpoint.text.trim());
      await storage.write(key: 'apiKey', value: apiKey.text.trim());
      if (scan) await request('/scan', post: true);
      final s = await request('/status') as Map<String, dynamic>;
      final c = await request('/changes') as List<dynamic>;
      if (!mounted) return;
      setState(() { status = s; changes = c; message = s['last_error']?.toString().isNotEmpty == true ? 'Błąd skanowania: ${s['last_error']}' : 'Dane aktualne'; });
    } catch (e) {
      if (mounted) setState(() => message = 'Nie udało się połączyć: $e');
    } finally { if (mounted) setState(() => loading = false); }
  }
  @override
  void dispose() { endpoint.dispose(); apiKey.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Monitor SharePoint')),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      const Text('BOK / Technologie', style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold)),
      const SizedBox(height: 12),
      TextField(controller: endpoint, decoration: const InputDecoration(labelText: 'Adres serwera HTTPS', hintText: 'https://monitor.example.com')),
      TextField(controller: apiKey, obscureText: true, decoration: const InputDecoration(labelText: 'Klucz API')),
      const SizedBox(height: 12),
      Wrap(spacing: 8, runSpacing: 8, children: [
        FilledButton.icon(onPressed: loading ? null : () => refresh(), icon: const Icon(Icons.refresh), label: const Text('Odśwież')),
        OutlinedButton.icon(onPressed: loading ? null : () => refresh(scan: true), icon: const Icon(Icons.manage_search), label: const Text('Skanuj teraz')),
        TextButton.icon(onPressed: () => launchUrl(Uri.parse('https://verifiseu.sharepoint.com/:f:/s/BOK/IgDGnd_NVbGPR52CXi-A-DbIAY-L_0hk2LjxEMRRQikdLn0?e=5%3awbm8QX&at=9'), mode: LaunchMode.externalApplication), icon: const Icon(Icons.login), label: const Text('Otwórz SharePoint')),
      ]),
      if (loading) const LinearProgressIndicator(),
      Padding(padding: const EdgeInsets.symmetric(vertical: 12), child: Text(message)),
      Card(child: ListTile(title: Text('Pliki: ${status['file_count'] ?? '—'}'), subtitle: Text('Ostatni skan: ${status['last_scan'] ?? 'brak'}'))),
      const SizedBox(height: 12),
      const Text('Historia zmian', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
      if (changes.isEmpty) const ListTile(title: Text('Brak zarejestrowanych zmian'), subtitle: Text('Pierwszy skan tworzy punkt odniesienia.')),
      ...changes.map((item) => Card(child: ListTile(
        leading: Icon(item['kind'] == 'nowy' ? Icons.note_add : item['kind'] == 'usuniety' ? Icons.delete_outline : Icons.edit_document),
        title: Text(item['name']?.toString() ?? ''),
        subtitle: Text('${item['kind']} · ${item['path']}\n${item['scanned_at']}'),
        isThreeLine: true,
      ))),
    ]),
  );
}
