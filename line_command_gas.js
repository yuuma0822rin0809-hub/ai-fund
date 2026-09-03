/**
 * 株シグナル通知 — LINE コマンド受付（Google Apps Script 用）
 *
 * LINE のトークに送った文字で watchlist.json を編集する。
 *   一覧              … 登録中の銘柄を返す
 *   追加 7203         … 銘柄を追加（銘柄名は自動で調べる）
 *   追加 7203 トヨタ   … 銘柄名を自分で指定して追加
 *   名前 7203 トヨタ   … 登録済み銘柄の名前だけ変更
 *   削除 7203         … 銘柄を削除
 *   ヘルプ            … 使い方を返す
 *
 * 事前にスクリプトプロパティへ以下を設定すること。
 *   LINE_TOKEN       : LINE のチャネルアクセストークン（長期）
 *   GITHUB_TOKEN     : GitHub の個人アクセストークン（ai-fund の Contents 書き込み権限）
 *   ALLOWED_USER_ID  : 自分の LINE ユーザーID（任意。設定すると他人からの操作を無視する）
 *   WEBHOOK_KEY      : 合言葉（任意。設定したら Webhook URL の末尾に ?k=合言葉 を付ける）
 */

var REPO = 'yuuma0822rin0809-hub/ai-fund';
var BRANCH = 'main';
var FILE_PATH = 'watchlist.json';

var GITHUB_API = 'https://api.github.com/repos/' + REPO + '/contents/' + FILE_PATH;
var LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply';


function prop(name) {
  return PropertiesService.getScriptProperties().getProperty(name) || '';
}


/** LINE からの受け口。必ず 200 を返す（エラーでも LINE に再送させない）。 */
function doPost(e) {
  var ok = ContentService.createTextOutput('OK');
  try {
    var key = prop('WEBHOOK_KEY');
    if (key && (!e.parameter || e.parameter.k !== key)) {
      console.log('合言葉が一致しないリクエストを無視しました');
      return ok;
    }
    var body = JSON.parse(e.postData.contents);
    var events = body.events || [];
    for (var i = 0; i < events.length; i++) {
      handleEvent(events[i]);
    }
  } catch (err) {
    console.log('doPost エラー: ' + err);
  }
  return ok;
}


/** 動作確認用。ブラウザでURLを開くとこの文字が出れば公開できている。 */
function doGet() {
  return ContentService.createTextOutput('kabu-signal command endpoint is running');
}


function handleEvent(ev) {
  if (ev.type !== 'message' || !ev.message || ev.message.type !== 'text') return;

  var allowed = prop('ALLOWED_USER_ID');
  if (allowed && ev.source && ev.source.userId !== allowed) {
    console.log('許可外のユーザーからの操作を無視しました');
    return;
  }

  var reply;
  try {
    reply = runCommand(ev.message.text);
  } catch (err) {
    reply = 'エラーが起きました。\n' + err;
  }
  replyToLine(ev.replyToken, reply);
}


function runCommand(rawText) {
  var text = String(rawText || '').replace(/　/g, ' ').trim();
  var parts = text.split(/\s+/);
  var cmd = (parts[0] || '').toLowerCase();

  if (cmd === '一覧' || cmd === 'リスト' || cmd === 'list') {
    return formatList(readWatchlist());
  }

  if (cmd === 'ヘルプ' || cmd === 'help' || cmd === '使い方') {
    return helpText();
  }

  if (cmd === '追加' || cmd === 'add') {
    if (!parts[1]) return '銘柄コードがありません。\n例：追加 7203';
    return addTicker(parts[1], parts.slice(2).join(' '));
  }

  if (cmd === '削除' || cmd === 'delete' || cmd === 'del') {
    if (!parts[1]) return '銘柄コードがありません。\n例：削除 7203';
    return removeTicker(parts[1]);
  }

  if (cmd === '名前' || cmd === 'name') {
    if (!parts[1] || !parts[2]) return '書き方が違います。\n例：名前 7203 トヨタ自動車';
    return renameTicker(parts[1], parts.slice(2).join(' '));
  }

  return 'コマンドが分かりませんでした。\n\n' + helpText();
}


function helpText() {
  return [
    '使い方',
    '',
    '一覧',
    '　登録中の銘柄を表示',
    '',
    '追加 7203',
    '　銘柄を追加（名前は自動で調べます）',
    '',
    '追加 7203 トヨタ',
    '　名前を指定して追加',
    '',
    '名前 7203 トヨタ自動車',
    '　登録済みの名前を変更',
    '',
    '削除 7203',
    '　銘柄を削除',
    '',
    '※ 日本株は4桁の数字だけでOK（.T は自動で付けます）',
    '※ 米国株は AAPL のようにそのまま'
  ].join('\n');
}


/** 入力されたコードを Yahoo ファイナンスの形に整える。 */
function normalizeCode(input) {
  var code = String(input || '').trim().toUpperCase();
  code = code.replace(/[０-９Ａ-Ｚ]/g, function (c) {
    return String.fromCharCode(c.charCodeAt(0) - 0xFEE0);
  });
  if (/^\d{4}$/.test(code) || /^\d{3}[A-Z]$/.test(code)) {
    code = code + '.T';
  }
  return code;
}


/** 日本株なら Yahoo ファイナンスのページ見出しから会社名を拾う。失敗しても落とさない。 */
function lookupName(code) {
  if (!/\.T$/.test(code)) return '';
  try {
    var res = UrlFetchApp.fetch('https://finance.yahoo.co.jp/quote/' + encodeURIComponent(code), {
      muteHttpExceptions: true,
      followRedirects: true
    });
    if (res.getResponseCode() !== 200) return '';
    var m = res.getContentText().match(/<title>([^<]+)<\/title>/);
    if (!m) return '';
    var title = m[1];
    var name = title.split('【')[0];
    name = name.replace(/\(株\)/g, '').replace(/株式会社/g, '').trim();
    return name.length > 0 && name.length <= 20 ? name : '';
  } catch (err) {
    console.log('銘柄名の取得に失敗: ' + err);
    return '';
  }
}


function githubHeaders() {
  var token = prop('GITHUB_TOKEN');
  if (!token) throw new Error('GITHUB_TOKEN がスクリプトプロパティに設定されていません。');
  return {
    Authorization: 'Bearer ' + token,
    Accept: 'application/vnd.github+json'
  };
}


function readWatchlist() {
  var res = UrlFetchApp.fetch(GITHUB_API + '?ref=' + BRANCH, {
    headers: githubHeaders(),
    muteHttpExceptions: true
  });
  if (res.getResponseCode() !== 200) {
    throw new Error('watchlist.json を読めませんでした（' + res.getResponseCode() + '）');
  }
  var meta = JSON.parse(res.getContentText());
  var text = Utilities.newBlob(
    Utilities.base64Decode(meta.content.replace(/\n/g, ''))
  ).getDataAsString();
  var data = JSON.parse(text);
  data.tickers = data.tickers || [];
  data.names = data.names || {};
  data.__sha = meta.sha;
  return data;
}


function writeWatchlist(data, message) {
  var sha = data.__sha;
  var out = { tickers: data.tickers, names: data.names };
  var text = JSON.stringify(out, null, 2) + '\n';
  var res = UrlFetchApp.fetch(GITHUB_API, {
    method: 'put',
    headers: githubHeaders(),
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify({
      message: message,
      content: Utilities.base64Encode(Utilities.newBlob(text).getBytes()),
      sha: sha,
      branch: BRANCH
    })
  });
  if (res.getResponseCode() >= 300) {
    throw new Error('watchlist.json を保存できませんでした（' + res.getResponseCode() + '）');
  }
}


function addTicker(input, givenName) {
  var code = normalizeCode(input);
  var data = readWatchlist();

  if (data.tickers.indexOf(code) >= 0) {
    var already = data.names[code] ? data.names[code] + '（' + code + '）' : code;
    return already + ' はすでに登録されています。';
  }

  var name = (givenName || '').trim() || lookupName(code);
  data.tickers.push(code);
  if (name) data.names[code] = name;

  writeWatchlist(data, 'chore: add ' + code + ' via LINE');

  var shown = name ? name + '（' + code + '）' : code;
  var note = name ? '' : '\n※ 銘柄名は取れませんでした。「名前 ' + input + ' ○○」で付けられます。';
  return '追加しました。\n■ ' + shown + '\n\n現在 ' + data.tickers.length + ' 銘柄を監視中です。' + note;
}


function removeTicker(input) {
  var code = normalizeCode(input);
  var data = readWatchlist();
  var idx = data.tickers.indexOf(code);
  if (idx < 0) return code + ' は登録されていません。\n「一覧」で確認できます。';

  var shown = data.names[code] ? data.names[code] + '（' + code + '）' : code;
  data.tickers.splice(idx, 1);
  delete data.names[code];

  writeWatchlist(data, 'chore: remove ' + code + ' via LINE');
  return '削除しました。\n■ ' + shown + '\n\n現在 ' + data.tickers.length + ' 銘柄を監視中です。';
}


function renameTicker(input, newName) {
  var code = normalizeCode(input);
  var data = readWatchlist();
  if (data.tickers.indexOf(code) < 0) return code + ' は登録されていません。';

  data.names[code] = newName.trim();
  writeWatchlist(data, 'chore: rename ' + code + ' via LINE');
  return '名前を変更しました。\n■ ' + data.names[code] + '（' + code + '）';
}


function formatList(data) {
  if (data.tickers.length === 0) return '登録されている銘柄はありません。';
  var lines = ['監視中の銘柄（' + data.tickers.length + '件）', ''];
  for (var i = 0; i < data.tickers.length; i++) {
    var code = data.tickers[i];
    var name = data.names[code];
    lines.push('■ ' + (name ? name + '（' + code + '）' : code));
  }
  lines.push('');
  lines.push('※ 判定が変わった翌朝に通知します');
  return lines.join('\n');
}


function replyToLine(replyToken, text) {
  var token = prop('LINE_TOKEN');
  if (!token || !replyToken) return;
  UrlFetchApp.fetch(LINE_REPLY_URL, {
    method: 'post',
    headers: { Authorization: 'Bearer ' + token },
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify({
      replyToken: replyToken,
      messages: [{ type: 'text', text: String(text).slice(0, 4900) }]
    })
  });
}
