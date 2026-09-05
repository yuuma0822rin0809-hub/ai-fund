/**
 * 株シグナル通知 — LINE コマンド受付（Google Apps Script 用）
 *
 * 銘柄の管理
 *   一覧                    … 登録中の銘柄と保有状況を表示
 *   追加 7203               … 銘柄を追加（銘柄名は自動で調べる）
 *   追加 7203 トヨタ         … 銘柄名を指定して追加
 *   名前 7203 トヨタ自動車    … 銘柄名だけ変更
 *   名前補完                … 名前が空の銘柄をまとめて調べ直す
 *   削除 7203               … 銘柄を削除
 *
 * 保有と目標
 *   保有 7203 100 2500      … 100株を平均2,500円で保有、と登録
 *   買増 7203 100 2600      … 100株を2,600円で買い足した（株数と平均取得単価を自動計算）
 *   売却 7203 50            … 50株売った（株数だけ減らす。全部売ると保有登録が消える）
 *   売却 7203 全部          … 全株売却
 *   保有削除 7203           … 保有の登録を消す
 *   目標 7203 30000         … 含み益が+30,000円になったら通知
 *   目標 7203 10%           … 含み益が+10%になったら通知
 *   損切 7203 -15000        … 含み損が-15,000円になったら通知
 *   損切 7203 -5%           … 含み損が-5%になったら通知
 *   目標解除 7203 / 損切解除 7203
 *
 * まとめて送る
 *   1つのメッセージに1行1コマンドで書くと、上から順にまとめて処理する。
 *     保有 7974 300 7500
 *     保有 8136 200 1300
 *     目標 7974 50000
 *
 * 通知の切り替え
 *   通知 判定  … 判定が切り替わったときだけ
 *   通知 利益  … 目標・損切りに到達したときだけ
 *   通知 両方  … どちらでも（初期設定）
 *   通知      … 今の設定を表示
 *
 *   ヘルプ    … 使い方を表示
 *
 * スクリプトプロパティ
 *   LINE_TOKEN       : LINE のチャネルアクセストークン（長期）
 *   GITHUB_TOKEN     : GitHub の個人アクセストークン（ai-fund の Contents 書き込み権限）
 *   ALLOWED_USER_ID  : 自分の LINE ユーザーID（任意）
 *   WEBHOOK_KEY      : 合言葉（任意）
 */

var REPO = 'yuuma0822rin0809-hub/ai-fund';
var BRANCH = 'main';
var WATCHLIST_PATH = 'watchlist.json';
var HOLDINGS_PATH = 'holdings.json';

var GITHUB_BASE = 'https://api.github.com/repos/' + REPO + '/contents/';
var LINE_REPLY_URL = 'https://api.line.me/v2/bot/message/reply';

var MODE_LABEL = {
  both: '両方（判定の切り替わり＋利益・損切り）',
  signal: '判定の切り替わりだけ',
  profit: '利益・損切りの到達だけ'
};


function prop(name) {
  return PropertiesService.getScriptProperties().getProperty(name) || '';
}


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

  replyToLine(ev.replyToken, runMessage(ev.message.text));
}


/** 1メッセージに複数行あれば、1行を1コマンドとして順番に処理する。 */
function runMessage(rawText) {
  var lines = String(rawText || '').split(/\r?\n/);
  var commands = [];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].replace(/　/g, ' ').trim();
    if (line) commands.push(line);
  }

  if (commands.length === 0) return helpText();

  if (commands.length === 1) {
    try {
      return runCommand(commands[0]);
    } catch (err) {
      return 'エラーが起きました。\n' + err;
    }
  }

  var results = [];
  var okCount = 0;
  for (var j = 0; j < commands.length; j++) {
    var result;
    try {
      result = runCommand(commands[j]);
      okCount++;
    } catch (err) {
      result = 'エラー: ' + err;
    }
    results.push('▶ ' + commands[j] + '\n' + result);
  }
  var header = commands.length + '件を処理しました（成功 ' + okCount + '件）\n\n';
  return header + results.join('\n\n────────\n\n');
}


function runCommand(rawText) {
  var text = String(rawText || '').replace(/　/g, ' ').trim();
  var parts = text.split(/\s+/);
  var cmd = (parts[0] || '').toLowerCase();

  if (cmd === '一覧' || cmd === 'リスト' || cmd === 'list') return showList();
  if (cmd === 'ヘルプ' || cmd === 'help' || cmd === '使い方') return helpText();

  if (cmd === '通知') return setMode(parts[1]);

  if (cmd === '追加' || cmd === 'add') {
    if (!parts[1]) return '銘柄コードがありません。\n例：追加 7203';
    return addTicker(parts[1], parts.slice(2).join(' '));
  }

  if (cmd === '削除' || cmd === 'delete' || cmd === 'del') {
    if (!parts[1]) return '銘柄コードがありません。\n例：削除 7203';
    return removeTicker(parts[1]);
  }

  if (cmd === '名前補完' || cmd === '名前確認') return fillMissingNames();

  if (cmd === '名前' || cmd === 'name') {
    if (!parts[1] || !parts[2]) return '書き方が違います。\n例：名前 7203 トヨタ自動車';
    return renameTicker(parts[1], parts.slice(2).join(' '));
  }

  if (cmd === '保有') {
    if (!parts[1] || !parts[2] || !parts[3]) {
      return '書き方が違います。\n例：保有 7203 100 2500\n（銘柄コード 株数 平均取得単価）';
    }
    return setHolding(parts[1], parts[2], parts[3]);
  }

  if (cmd === '保有削除') {
    if (!parts[1]) return '銘柄コードがありません。\n例：保有削除 7203';
    return removeHolding(parts[1]);
  }

  if (cmd === '買増' || cmd === '買い増し' || cmd === '買増し' || cmd === '追加購入') {
    if (!parts[1] || !parts[2] || !parts[3]) {
      return '書き方が違います。\n例：買増 7203 100 2600\n（銘柄コード 買い足した株数 買った単価）';
    }
    return addToHolding(parts[1], parts[2], parts[3]);
  }

  if (cmd === '売却' || cmd === '売った' || cmd === '一部売却') {
    if (!parts[1] || !parts[2]) {
      return '書き方が違います。\n例：売却 7203 50\n（銘柄コード 売った株数）\n全部売ったときは「売却 7203 全部」';
    }
    return sellFromHolding(parts[1], parts[2]);
  }

  if (cmd === '目標') {
    if (!parts[1] || !parts[2]) return '書き方が違います。\n例：目標 7203 30000\n　　目標 7203 10%';
    return setThreshold(parts[1], parts[2], 'target');
  }

  if (cmd === '損切' || cmd === '損切り') {
    if (!parts[1] || !parts[2]) return '書き方が違います。\n例：損切 7203 -15000\n　　損切 7203 -5%';
    return setThreshold(parts[1], parts[2], 'stop');
  }

  if (cmd === '目標解除') return clearThreshold(parts[1], 'target');
  if (cmd === '損切解除' || cmd === '損切り解除') return clearThreshold(parts[1], 'stop');

  return 'コマンドが分かりませんでした。\n\n' + helpText();
}


function helpText() {
  return [
    '【銘柄の管理】',
    '一覧',
    '追加 7203',
    '追加 7203 トヨタ',
    '名前 7203 トヨタ自動車',
    '名前補完（名前が空の銘柄をまとめて調べ直す）',
    '削除 7203',
    '',
    '【保有と目標】',
    '保有 7203 100 2500',
    '　（コード 株数 平均取得単価）',
    '買増 7203 100 2600',
    '　（買い足した株数と単価。平均取得単価は自動計算）',
    '売却 7203 50 / 売却 7203 全部',
    '保有削除 7203',
    '目標 7203 30000',
    '目標 7203 10%',
    '損切 7203 -15000',
    '損切 7203 -5%',
    '目標解除 7203 / 損切解除 7203',
    '',
    '【まとめて送る】',
    '1行に1コマンドで複数行書くと、',
    '上から順にまとめて処理します。',
    '',
    '【通知の切り替え】',
    '通知 判定',
    '通知 利益',
    '通知 両方',
    '通知（今の設定を表示）',
    '',
    '※ 日本株は4桁の数字だけでOK',
    '※ 米国株は AAPL のようにそのまま'
  ].join('\n');
}


function normalizeCode(input) {
  var code = String(input || '').trim().toUpperCase();
  code = code.replace(/[０-９Ａ-Ｚ％]/g, function (c) {
    return String.fromCharCode(c.charCodeAt(0) - 0xFEE0);
  });
  if (/^\d{4}$/.test(code) || /^\d{3}[A-Z]$/.test(code)) code = code + '.T';
  return code;
}


function toHalfWidth(text) {
  return String(text || '').replace(/[０-９％．－]/g, function (c) {
    if (c === '．') return '.';
    if (c === '－') return '-';
    return String.fromCharCode(c.charCodeAt(0) - 0xFEE0);
  });
}


function currencyOf(code) {
  return /\.T$/.test(code) ? '¥' : '$';
}


function lookupName(code) {
  // Yahoo!ファイナンス（日本版）は米国株にも日本語名のページがある。
  // 短時間に続けて叩くと弾かれることがあるので、少し待ってから最大3回試す。
  var url = 'https://finance.yahoo.co.jp/quote/' + encodeURIComponent(code);
  for (var attempt = 0; attempt < 3; attempt++) {
    try {
      if (attempt > 0) Utilities.sleep(1500 * attempt);
      var res = UrlFetchApp.fetch(url, {
        muteHttpExceptions: true,
        followRedirects: true,
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
      });
      if (res.getResponseCode() !== 200) continue;
      var m = res.getContentText().match(/<title>([^<]+)<\/title>/);
      if (!m) continue;
      var title = m[1];
      if (title.indexOf('【') < 0) continue;
      var name = title.split('【')[0].replace(/\(株\)/g, '').replace(/株式会社/g, '').trim();
      if (name.length > 0 && name.length <= 24) return name;
    } catch (err) {
      console.log('銘柄名の取得に失敗 (' + code + ', ' + (attempt + 1) + '回目): ' + err);
    }
  }
  return '';
}


/** 名前が空の銘柄をまとめて調べ直す。 */
function fillMissingNames() {
  var watch = readWatchlist();
  var targets = [];
  for (var i = 0; i < watch.tickers.length; i++) {
    var code = watch.tickers[i];
    if (!watch.names[code]) targets.push(code);
  }
  if (targets.length === 0) return 'すべての銘柄に名前が付いています。';

  var found = [];
  var failed = [];
  for (var j = 0; j < targets.length; j++) {
    var c = targets[j];
    var name = lookupName(c);
    if (name) {
      watch.names[c] = name;
      found.push('■ ' + name + '（' + c + '）');
    } else {
      failed.push(c);
    }
    if (j < targets.length - 1) Utilities.sleep(800);
  }

  if (found.length > 0) {
    writeJson(WATCHLIST_PATH, watch, 'chore: fill ' + found.length + ' names via LINE');
  }

  var lines = [];
  if (found.length > 0) {
    lines.push('名前を付けました（' + found.length + '件）');
    lines = lines.concat(found);
  }
  if (failed.length > 0) {
    lines.push('');
    lines.push('取れなかった銘柄（' + failed.length + '件）');
    lines.push(failed.join(' / '));
    lines.push('「名前 コード 名称」で付けてください。');
  }
  return lines.join('\n');
}


function githubHeaders() {
  var token = prop('GITHUB_TOKEN');
  if (!token) throw new Error('GITHUB_TOKEN がスクリプトプロパティに設定されていません。');
  return { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' };
}


/** GitHub 上の JSON を読む。無ければ fallback を返す（sha は null）。 */
function readJson(path, fallback) {
  var res = UrlFetchApp.fetch(GITHUB_BASE + path + '?ref=' + BRANCH, {
    headers: githubHeaders(),
    muteHttpExceptions: true
  });
  if (res.getResponseCode() === 404) {
    var empty = JSON.parse(JSON.stringify(fallback));
    empty.__sha = null;
    return empty;
  }
  if (res.getResponseCode() !== 200) {
    throw new Error(path + ' を読めませんでした（' + res.getResponseCode() + '）');
  }
  var meta = JSON.parse(res.getContentText());
  var text = Utilities.newBlob(Utilities.base64Decode(meta.content.replace(/\n/g, ''))).getDataAsString();
  var data = JSON.parse(text);
  data.__sha = meta.sha;
  return data;
}


function writeJson(path, data, message) {
  var sha = data.__sha;
  var out = JSON.parse(JSON.stringify(data));
  delete out.__sha;
  var text = JSON.stringify(out, null, 2) + '\n';
  var payload = {
    message: message,
    content: Utilities.base64Encode(Utilities.newBlob(text).getBytes()),
    branch: BRANCH
  };
  if (sha) payload.sha = sha;

  var res = UrlFetchApp.fetch(GITHUB_BASE + path, {
    method: 'put',
    headers: githubHeaders(),
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify(payload)
  });
  if (res.getResponseCode() >= 300) {
    throw new Error(path + ' を保存できませんでした（' + res.getResponseCode() + '）');
  }
}


function readWatchlist() {
  var data = readJson(WATCHLIST_PATH, { tickers: [], names: {} });
  data.tickers = data.tickers || [];
  data.names = data.names || {};
  return data;
}


function readHoldings() {
  var data = readJson(HOLDINGS_PATH, { notify_mode: 'both', holdings: {} });
  data.notify_mode = data.notify_mode || 'both';
  data.holdings = data.holdings || {};
  return data;
}


function nameOf(code, watch) {
  var n = watch.names[code];
  return n ? n + '（' + code + '）' : code;
}


// ---------- 銘柄の管理 ----------

function addTicker(input, givenName) {
  var code = normalizeCode(input);
  var watch = readWatchlist();

  if (watch.tickers.indexOf(code) >= 0) {
    return nameOf(code, watch) + ' はすでに登録されています。';
  }

  var name = (givenName || '').trim() || lookupName(code);
  watch.tickers.push(code);
  if (name) watch.names[code] = name;

  writeJson(WATCHLIST_PATH, watch, 'chore: add ' + code + ' via LINE');

  var shown = name ? name + '（' + code + '）' : code;
  var note = name ? '' : '\n※ 銘柄名は取れませんでした。「名前 ' + input + ' ○○」で付けられます。';
  return '追加しました。\n■ ' + shown + '\n\n現在 ' + watch.tickers.length + ' 銘柄を監視中です。' + note;
}


function removeTicker(input) {
  var code = normalizeCode(input);
  var watch = readWatchlist();
  var idx = watch.tickers.indexOf(code);
  if (idx < 0) return code + ' は登録されていません。\n「一覧」で確認できます。';

  var shown = nameOf(code, watch);
  watch.tickers.splice(idx, 1);
  delete watch.names[code];
  writeJson(WATCHLIST_PATH, watch, 'chore: remove ' + code + ' via LINE');

  var extra = '';
  var hold = readHoldings();
  if (hold.holdings[code]) {
    delete hold.holdings[code];
    writeJson(HOLDINGS_PATH, hold, 'chore: remove holding ' + code + ' via LINE');
    extra = '\n保有の登録も一緒に消しました。';
  }

  return '削除しました。\n■ ' + shown + '\n\n現在 ' + watch.tickers.length + ' 銘柄を監視中です。' + extra;
}


function renameTicker(input, newName) {
  var code = normalizeCode(input);
  var watch = readWatchlist();
  if (watch.tickers.indexOf(code) < 0) return code + ' は登録されていません。';
  watch.names[code] = newName.trim();
  writeJson(WATCHLIST_PATH, watch, 'chore: rename ' + code + ' via LINE');
  return '名前を変更しました。\n■ ' + watch.names[code] + '（' + code + '）';
}


// ---------- 保有と目標 ----------

function setHolding(codeInput, qtyInput, costInput) {
  var code = normalizeCode(codeInput);
  var qty = Number(toHalfWidth(qtyInput).replace(/[,株]/g, ''));
  var cost = Number(toHalfWidth(costInput).replace(/[,円$¥]/g, ''));

  if (!isFinite(qty) || qty <= 0) return '株数が読み取れませんでした。\n例：保有 7203 100 2500';
  if (!isFinite(cost) || cost <= 0) return '取得単価が読み取れませんでした。\n例：保有 7203 100 2500';

  var watch = readWatchlist();
  var added = '';
  if (watch.tickers.indexOf(code) < 0) {
    var name = lookupName(code);
    watch.tickers.push(code);
    if (name) watch.names[code] = name;
    writeJson(WATCHLIST_PATH, watch, 'chore: add ' + code + ' via LINE');
    added = '\n※ 監視銘柄にも追加しました。';
  }

  var hold = readHoldings();
  var entry = hold.holdings[code] || {};
  entry.qty = qty;
  entry.cost = cost;
  hold.holdings[code] = entry;
  writeJson(HOLDINGS_PATH, hold, 'chore: set holding ' + code + ' via LINE');

  var sym = currencyOf(code);
  var lines = [
    '保有を登録しました。',
    '■ ' + nameOf(code, watch),
    '　' + qty.toLocaleString() + '株 / 取得 ' + sym + cost.toLocaleString(),
    '　投資額 ' + sym + (qty * cost).toLocaleString()
  ];
  if (!entry.target && !entry.stop) {
    lines.push('');
    lines.push('※ 利益の通知には目標の設定が必要です。');
    lines.push('　例：目標 ' + codeInput + ' 30000');
  }
  return lines.join('\n') + added;
}


function removeHolding(input) {
  var code = normalizeCode(input);
  var hold = readHoldings();
  if (!hold.holdings[code]) return code + ' の保有は登録されていません。';
  delete hold.holdings[code];
  writeJson(HOLDINGS_PATH, hold, 'chore: remove holding ' + code + ' via LINE');
  return code + ' の保有登録を消しました。\n監視銘柄としては残っています。';
}


/** 買い増し：株数を足し、平均取得単価を計算し直す。 */
function addToHolding(codeInput, qtyInput, priceInput) {
  var code = normalizeCode(codeInput);
  var qty = Number(toHalfWidth(qtyInput).replace(/[,株]/g, ''));
  var price = Number(toHalfWidth(priceInput).replace(/[,円$¥]/g, ''));

  if (!isFinite(qty) || qty <= 0) return '株数が読み取れませんでした。\n例：買増 7203 100 2600';
  if (!isFinite(price) || price <= 0) return '単価が読み取れませんでした。\n例：買増 7203 100 2600';

  var hold = readHoldings();
  var entry = hold.holdings[code];
  if (!entry) {
    return code + ' の保有がまだ登録されていません。\n初回は「保有 ' + codeInput + ' 株数 取得単価」で登録してください。';
  }

  var oldQty = Number(entry.qty);
  var oldCost = Number(entry.cost);
  var newQty = oldQty + qty;
  var newCost = Math.round(((oldQty * oldCost + qty * price) / newQty) * 100) / 100;
  entry.qty = newQty;
  entry.cost = newCost;
  writeJson(HOLDINGS_PATH, hold, 'chore: add to holding ' + code + ' via LINE');

  var watch = readWatchlist();
  var sym = currencyOf(code);
  return [
    '買い増しを反映しました。',
    '■ ' + nameOf(code, watch),
    '　これまで ' + oldQty.toLocaleString() + '株（' + sym + oldCost.toLocaleString() + '）',
    '　＋ 今回 ' + qty.toLocaleString() + '株（' + sym + price.toLocaleString() + '）',
    '　→ ' + newQty.toLocaleString() + '株 / 平均取得 ' + sym + newCost.toLocaleString(),
    '　投資額 ' + sym + Math.round(newQty * newCost).toLocaleString()
  ].join('\n');
}


/** 売却：株数だけ減らす（平均取得単価は変わらない）。全部売ったら保有登録を消す。 */
function sellFromHolding(codeInput, qtyInput) {
  var code = normalizeCode(codeInput);
  var hold = readHoldings();
  var entry = hold.holdings[code];
  if (!entry) return code + ' の保有は登録されていません。';

  var oldQty = Number(entry.qty);
  var raw = toHalfWidth(qtyInput).replace(/[,株]/g, '');
  var qty = (raw === '全部' || raw === '全て' || raw === 'すべて' || raw.toLowerCase() === 'all') ? oldQty : Number(raw);
  if (!isFinite(qty) || qty <= 0) return '株数が読み取れませんでした。\n例：売却 7203 50';
  if (qty > oldQty) {
    return '保有は ' + oldQty.toLocaleString() + '株です。それより多くは売却できません。\n全部売ったなら「売却 ' + codeInput + ' 全部」を送ってください。';
  }

  var watch = readWatchlist();
  var sym = currencyOf(code);
  var newQty = oldQty - qty;

  if (newQty === 0) {
    delete hold.holdings[code];
    writeJson(HOLDINGS_PATH, hold, 'chore: sell all ' + code + ' via LINE');
    return '全株売却として保有登録を消しました。\n■ ' + nameOf(code, watch) + '\n監視銘柄としては残っています。';
  }

  entry.qty = newQty;
  writeJson(HOLDINGS_PATH, hold, 'chore: sell ' + qty + ' of ' + code + ' via LINE');
  return [
    '売却を反映しました。',
    '■ ' + nameOf(code, watch),
    '　' + oldQty.toLocaleString() + '株 → ' + newQty.toLocaleString() + '株（' + qty.toLocaleString() + '株売却）',
    '　平均取得 ' + sym + Number(entry.cost).toLocaleString() + '（変わりません）',
    '　投資額 ' + sym + Math.round(newQty * Number(entry.cost)).toLocaleString()
  ].join('\n');
}


function parseThreshold(input) {
  var text = toHalfWidth(input).replace(/[,円]/g, '').trim();
  var isPercent = /%$/.test(text);
  var num = Number(text.replace(/%$/, ''));
  if (!isFinite(num) || num === 0) return null;
  return { type: isPercent ? 'percent' : 'amount', value: num };
}


function setThreshold(codeInput, valueInput, kind) {
  var code = normalizeCode(codeInput);
  var rule = parseThreshold(valueInput);
  if (!rule) {
    return '数値が読み取れませんでした。\n例：' + (kind === 'target' ? '目標 7203 30000' : '損切 7203 -15000');
  }

  if (kind === 'target' && rule.value < 0) return '目標はプラスの数字で指定してください。\n例：目標 7203 30000';
  if (kind === 'stop' && rule.value > 0) return '損切りはマイナスの数字で指定してください。\n例：損切 7203 -15000';

  var hold = readHoldings();
  if (!hold.holdings[code]) {
    return code + ' の保有がまだ登録されていません。\n先に「保有 ' + codeInput + ' 株数 取得単価」を送ってください。';
  }
  hold.holdings[code][kind] = rule;
  writeJson(HOLDINGS_PATH, hold, 'chore: set ' + kind + ' for ' + code + ' via LINE');

  var watch = readWatchlist();
  var word = kind === 'target' ? '利益目標' : '損切りライン';
  return word + 'を設定しました。\n■ ' + nameOf(code, watch) + '\n　' + describeRule(rule, code);
}


function clearThreshold(codeInput, kind) {
  if (!codeInput) return '銘柄コードがありません。';
  var code = normalizeCode(codeInput);
  var hold = readHoldings();
  if (!hold.holdings[code] || !hold.holdings[code][kind]) return code + ' には設定されていません。';
  delete hold.holdings[code][kind];
  writeJson(HOLDINGS_PATH, hold, 'chore: clear ' + kind + ' for ' + code + ' via LINE');
  return code + ' の' + (kind === 'target' ? '利益目標' : '損切りライン') + 'を解除しました。';
}


function describeRule(rule, code) {
  if (!rule) return '未設定';
  if (rule.type === 'percent') return (rule.value > 0 ? '+' : '') + rule.value + '%';
  var sym = currencyOf(code);
  return (rule.value > 0 ? '+' : '-') + sym + Math.abs(rule.value).toLocaleString();
}


// ---------- 通知モード ----------

function setMode(arg) {
  var hold = readHoldings();

  if (!arg) {
    return '今の通知設定\n■ ' + (MODE_LABEL[hold.notify_mode] || hold.notify_mode) +
      '\n\n変えるには\n通知 判定 / 通知 利益 / 通知 両方';
  }

  var map = {
    '判定': 'signal', 'シグナル': 'signal', 'signal': 'signal',
    '利益': 'profit', '損益': 'profit', 'profit': 'profit',
    '両方': 'both', 'both': 'both', '全部': 'both'
  };
  var mode = map[arg];
  if (!mode) {
    return '「通知 判定」「通知 利益」「通知 両方」のどれかを送ってください。';
  }

  hold.notify_mode = mode;
  writeJson(HOLDINGS_PATH, hold, 'chore: set notify mode ' + mode + ' via LINE');
  return '通知設定を変更しました。\n■ ' + MODE_LABEL[mode];
}


// ---------- 一覧 ----------

function showList() {
  var watch = readWatchlist();
  var hold = readHoldings();

  if (watch.tickers.length === 0) return '登録されている銘柄はありません。';

  var lines = ['監視中の銘柄（' + watch.tickers.length + '件）', ''];
  for (var i = 0; i < watch.tickers.length; i++) {
    var code = watch.tickers[i];
    var sym = currencyOf(code);
    lines.push('■ ' + nameOf(code, watch));
    var h = hold.holdings[code];
    if (h) {
      lines.push('　保有 ' + Number(h.qty).toLocaleString() + '株 / 取得 ' + sym + Number(h.cost).toLocaleString());
      lines.push('　目標 ' + describeRule(h.target, code) + ' / 損切 ' + describeRule(h.stop, code));
    }
  }
  lines.push('');
  lines.push('通知設定：' + (MODE_LABEL[hold.notify_mode] || hold.notify_mode));
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
