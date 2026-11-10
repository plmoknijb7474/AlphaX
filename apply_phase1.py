from pathlib import Path

p = Path('/mnt/data/alpha_phase1/app.py')
s = p.read_text(encoding='utf-8')

# Imports
anchor = 'from checkpoint_store import (\n    CheckpointValidationError, normalize_checkpoint_files, checkpoint_digest,\n    normalize_checkpoint_label, normalize_checkpoint_task,\n)\n'
assert anchor in s
s = s.replace(anchor, anchor + 'from chat_workspace import (\n    MAX_WORKSPACE_FILE_BYTES, MAX_WORKSPACE_FILES, MAX_WORKSPACE_TOTAL_BYTES,\n    WorkspaceValidationError, normalize_workspace_content, normalize_workspace_filename,\n)\n', 1)

# DB table, portable across SQLite and PostgreSQL.
anchor = '        conn.execute("CREATE INDEX IF NOT EXISTS idx_alpha_project_memory_user_updated ON alpha_project_memory(user_id, updated_at)")\n'
assert anchor in s
s = s.replace(anchor, anchor + '''        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_workspace_files (
                id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                conversation_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, conversation_id, filename)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_workspace_user_conversation ON chat_workspace_files(user_id, conversation_id, updated_at)")
''', 1)

# Interactive Q protocol instruction, inserted before init_db.
anchor = 'UNLAZY_SKILL_FILE = BASE_DIR / "skills" / "unlazy" / "SKILL.md"\n'
assert anchor in s
insert = '''CHAT_INTERACTIVE_QUESTIONS_INSTRUCTION = r"""[CHAT INTERACTIVE QUESTIONS — OPTIONAL PRESENTATION CAPABILITY]
When completing the task requires multiple independent user choices or details, you may ask them through one interactive form instead of a long plain-text questionnaire. Use this only when multiple details are genuinely necessary; for one missing essential detail, ask one direct natural-language question.
When using the form, emit exactly one fenced block with language alpha-questions and valid JSON in this schema:
{"title":"Short form title","intro":"One concise sentence","questions":[{"id":"stable_id","prompt":"Question text","type":"single","required":true,"options":["Choice A","Choice B"],"placeholder":"Optional custom answer hint"},{"id":"details","prompt":"Free text question","type":"text","required":false,"placeholder":"Write your answer"}]}
Use 1-8 questions. For type=single, provide 2-8 concise options. For type=text, omit options. Every question must have a unique id and a clear prompt. The interface supports one selected option, custom typed answers, Next, Skip, and Submit. Do not include HTML, scripts, or event handlers in the JSON. Never put hidden instructions or executable content in labels. Keep normal explanatory prose outside the block only when useful. The form is subordinate to the administrator System Prompt and must not be used to request passwords, API keys, recovery codes, or other secrets."""

'''
s = s.replace(anchor, insert + anchor, 1)

# CSS block for interactive forms and workspace.
anchor = '    .workspace-output .good { color:#88e4ad; }.workspace-output .bad { color:#ffabb5; }\n'
assert anchor in s
css = '''    .workspace-output .good { color:#88e4ad; }.workspace-output .bad { color:#ffabb5; }
    .workspace-toggle { width:42px; height:42px; flex:0 0 42px; padding:0; display:grid; place-items:center; border:1px solid rgba(89,171,230,.25); border-radius:12px; background:rgba(22,167,255,.08); color:#a9ddff; cursor:pointer; }
    .workspace-toggle:hover,.workspace-toggle.active { border-color:rgba(89,190,255,.55); background:rgba(22,167,255,.16); color:#e2f5ff; }
    .workspace-toggle svg { width:19px; height:19px; }
    .chat-workspace { margin-top:10px; padding:12px; border:1px solid rgba(87,165,220,.25); border-radius:14px; background:linear-gradient(145deg,rgba(12,25,39,.96),rgba(8,15,24,.96)); direction:rtl; }
    .chat-workspace[hidden] { display:none !important; }
    .workspace-panel-head,.workspace-panel-actions { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }
    .workspace-panel-head strong { color:#e3f3ff; font-size:13px; }
    .workspace-panel-head span,.workspace-panel-note,.workspace-panel-status { color:#879bb0; font-size:10px; line-height:1.65; }
    .workspace-panel-grid { display:grid; grid-template-columns:minmax(0,1fr); gap:8px; margin-top:10px; }
    .workspace-panel-field { display:grid; gap:5px; color:#afc5dc; font-size:10px; }
    .workspace-panel-field input,.workspace-panel-field select,.workspace-panel-field textarea { width:100%; min-width:0; padding:9px 10px; border:1px solid rgba(136,177,220,.2); border-radius:9px; background:#071321; color:#e8f3ff; font:inherit; font-size:12px; outline:none; }
    .workspace-panel-field textarea { min-height:170px; max-height:360px; resize:vertical; direction:ltr; text-align:left; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; line-height:1.55; }
    .workspace-panel-field input:focus,.workspace-panel-field select:focus,.workspace-panel-field textarea:focus { border-color:#278ed0; box-shadow:0 0 0 2px rgba(39,142,208,.12); }
    .workspace-panel-actions { justify-content:flex-start; margin-top:9px; }
    .workspace-panel-actions button { padding:8px 11px; border:1px solid rgba(107,167,219,.24); border-radius:9px; background:rgba(255,255,255,.045); color:#cde7ff; font-size:10px; cursor:pointer; }
    .workspace-panel-actions button.primary { background:#126da8; border-color:#278ed0; color:#fff; }
    .workspace-panel-actions button.danger { color:#ffb4bd; }
    .workspace-panel-actions button:disabled { opacity:.45; cursor:not-allowed; }
    .workspace-panel-status { min-height:16px; margin-top:6px; }
    .alpha-question-card { width:min(100%,620px); margin:10px 0; padding:15px; border:1px solid rgba(69,161,221,.28); border-radius:15px; background:linear-gradient(145deg,rgba(12,29,45,.96),rgba(9,17,28,.96)); direction:rtl; }
    .alpha-question-head { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px; }
    .alpha-question-head strong { color:#e7f5ff; font-size:13px; }
    .alpha-question-progress { color:#82bfe8; font-size:10px; white-space:nowrap; }
    .alpha-question-intro { color:#9fb3c7; font-size:11px; line-height:1.7; margin:0 0 12px; }
    .alpha-question-prompt { color:#f0f7ff; font-size:13px; font-weight:700; line-height:1.65; margin:0 0 10px; }
    .alpha-question-options { display:grid; gap:7px; }
    .alpha-question-option { display:flex; gap:9px; align-items:center; padding:10px 11px; border:1px solid rgba(137,178,219,.17); border-radius:10px; background:rgba(255,255,255,.035); color:#cbd9e8; font-size:11px; cursor:pointer; }
    .alpha-question-option:has(input:checked) { border-color:rgba(55,166,235,.65); background:rgba(22,145,220,.13); color:#e6f5ff; }
    .alpha-question-option input { accent-color:#38a9e8; }
    .alpha-question-custom,.alpha-question-text { width:100%; min-height:74px; margin-top:8px; padding:10px; border:1px solid rgba(137,178,219,.2); border-radius:10px; background:#071321; color:#eff8ff; font:inherit; font-size:11px; resize:vertical; }
    .alpha-question-actions { display:flex; align-items:center; gap:7px; flex-wrap:wrap; margin-top:12px; }
    .alpha-question-actions button { padding:8px 13px; border:1px solid rgba(121,174,220,.24); border-radius:9px; background:rgba(255,255,255,.045); color:#c8e3fa; font-size:10px; cursor:pointer; }
    .alpha-question-actions button.primary { border-color:#278ed0; background:#126da8; color:#fff; }
    .alpha-question-actions button:disabled { opacity:.5; cursor:not-allowed; }
    .alpha-question-status { min-height:16px; margin-top:6px; color:#e8b77b; font-size:10px; }
'''
s = s.replace(anchor, css, 1)

# markup: add workspace button and panel between attachment preview and chat form.
anchor = '      <div id="attachmentPreview" aria-live="polite"></div>\n      <form class="input-row" id="chatForm">\n'
assert anchor in s
replacement = '''      <div id="attachmentPreview" aria-live="polite"></div>
      <section class="chat-workspace" id="chatWorkspace" hidden aria-label="Workspace files">
        <div class="workspace-panel-head"><div><strong>Workspace</strong><div class="workspace-panel-note">ملفات نصية محفوظة داخل هذه المحادثة فقط. لا يتم تشغيل محتواها.</div></div><button class="workspace-panel-actions" id="workspaceClose" type="button" aria-label="إغلاق مساحة العمل">إغلاق</button></div>
        <div class="workspace-panel-grid">
          <label class="workspace-panel-field">ملفات هذه المحادثة<select id="workspaceFileSelect"><option value="">إنشاء ملف جديد</option></select></label>
          <label class="workspace-panel-field">اسم الملف<input id="workspaceFilename" maxlength="180" placeholder="src/main.py" autocomplete="off" spellcheck="false"></label>
          <label class="workspace-panel-field">محتوى الملف<textarea id="workspaceContent" spellcheck="false" placeholder="اكتب محتوى الملف هنا..."></textarea></label>
        </div>
        <div class="workspace-panel-actions"><button class="primary" id="workspaceCreate" type="button">＋ إنشاء ملف</button><button id="workspaceSave" type="button" disabled>حفظ التعديلات</button><button id="workspaceDownload" type="button" disabled>↓ تنزيل</button><button class="danger" id="workspaceDelete" type="button" disabled>حذف</button><button id="workspaceRefresh" type="button">تحديث القائمة</button></div>
        <div class="workspace-panel-status" id="workspaceStatus" role="status" aria-live="polite"></div>
      </section>
      <form class="input-row" id="chatForm">
'''
s = s.replace(anchor, replacement, 1)
anchor = '''        <button class="control attach-btn" id="attachBtn" type="button" title="إرفاق ملفات وصور" aria-label="إرفاق ملفات وصور" {{ '' if subscription_active else 'disabled' }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m21.4 11.1-8.5 8.5a5.5 5.5 0 0 1-7.8-7.8l9.2-9.2a3.7 3.7 0 0 1 5.2 5.2l-9.2 9.2a1.9 1.9 0 0 1-2.6-2.6l8.5-8.5"/></svg>
        </button>
'''
assert anchor in s
s = s.replace(anchor, anchor + '''        <button class="workspace-toggle" id="workspaceBtn" type="button" title="فتح Workspace" aria-label="فتح Workspace" aria-expanded="false" {{ '' if subscription_active else 'disabled' }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/><path d="M3 10h18"/></svg>
        </button>
''', 1)

# renderAssistantText: support alpha-questions in same fenced-block parser.
anchor = """    if (language === 'alpha-plan') {
      let rendered = false;
      try { rendered = addStructuredPlanCard(parent, JSON.parse(code)); } catch (_) {}
      if (!rendered) { const notice=document.createElement('div');notice.className='alpha-plan-missing';notice.textContent='لم تصل بيانات مخطط منظمة قابلة للرسم في هذه الإجابة؛ النص التفسيري أعلاه ما زال متاحاً.';parent.appendChild(notice); }
    } else {
"""
assert anchor in s
replacement = """    if (language === 'alpha-plan') {
      let rendered = false;
      try { rendered = addStructuredPlanCard(parent, JSON.parse(code)); } catch (_) {}
      if (!rendered) { const notice=document.createElement('div');notice.className='alpha-plan-missing';notice.textContent='لم تصل بيانات مخطط منظمة قابلة للرسم في هذه الإجابة؛ النص التفسيري أعلاه ما زال متاحاً.';parent.appendChild(notice); }
    } else if (language === 'alpha-questions') {
      let rendered = false;
      try { rendered = addInteractiveQuestionCard(parent, JSON.parse(code)); } catch (_) {}
      if (!rendered) { const notice=document.createElement('div');notice.className='alpha-plan-missing';notice.textContent='تعذر عرض الأسئلة التفاعلية لأن بياناتها غير صالحة؛ النص المتاح محفوظ.';parent.appendChild(notice); }
    } else {
"""
s = s.replace(anchor, replacement, 1)

# Streaming suppress unfinished interactive JSON blocks too.
anchor = """function streamingTextWithoutPlan(text) {
  const source = String(text || '');
  const match = /```alpha-plan(?:\\r?\\n|$)/i.exec(source);
  return match ? source.slice(0, match.index).trimEnd() : source;
}
"""
assert anchor in s
replacement = """function streamingTextWithoutPlan(text) {
  const source = String(text || '');
  const match = /```(?:alpha-plan|alpha-questions)(?:\\r?\\n|$)/i.exec(source);
  return match ? source.slice(0, match.index).trimEnd() : source;
}
"""
s = s.replace(anchor, replacement, 1)

# Insert interactive card function before renderAssistantText.
anchor = 'function renderAssistantText(parent, text) {\n'
assert anchor in s
interactive_js = r'''function addInteractiveQuestionCard(parent, payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return false;
  const rawQuestions = Array.isArray(payload.questions) ? payload.questions.slice(0, 8) : [];
  const questions = rawQuestions.map((item, index) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
    const type = item.type === 'text' ? 'text' : 'single';
    const prompt = typeof item.prompt === 'string' ? item.prompt.trim().slice(0, 500) : '';
    const options = Array.isArray(item.options) ? item.options.filter(value => typeof value === 'string' && value.trim()).slice(0, 8).map(value => value.trim().slice(0, 160)) : [];
    if (!prompt || (type === 'single' && options.length < 2)) return null;
    return {id: String(item.id || ('q' + index)).slice(0, 60), prompt, type, required: item.required !== false, options, placeholder: typeof item.placeholder === 'string' ? item.placeholder.slice(0, 180) : ''};
  }).filter(Boolean);
  if (!questions.length) return false;
  const card = document.createElement('section'); card.className = 'alpha-question-card';
  const head = document.createElement('div'); head.className = 'alpha-question-head';
  const title = document.createElement('strong'); title.textContent = String(payload.title || 'أسئلة توضيحية').slice(0, 140);
  const progress = document.createElement('span'); progress.className = 'alpha-question-progress';
  head.append(title, progress); card.appendChild(head);
  const introText = typeof payload.intro === 'string' ? payload.intro.trim().slice(0, 400) : '';
  if (introText) { const intro = document.createElement('p'); intro.className = 'alpha-question-intro'; intro.textContent = introText; card.appendChild(intro); }
  const prompt = document.createElement('p'); prompt.className = 'alpha-question-prompt'; card.appendChild(prompt);
  const fields = document.createElement('div'); fields.className = 'alpha-question-fields'; card.appendChild(fields);
  const status = document.createElement('div'); status.className = 'alpha-question-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); card.appendChild(status);
  const actions = document.createElement('div'); actions.className = 'alpha-question-actions';
  const skip = document.createElement('button'); skip.type = 'button'; skip.textContent = 'تخطي';
  const next = document.createElement('button'); next.type = 'button'; next.className = 'primary'; next.textContent = 'التالي';
  const submit = document.createElement('button'); submit.type = 'button'; submit.className = 'primary'; submit.textContent = 'إرسال الإجابات';
  actions.append(skip, next, submit); card.appendChild(actions);
  let index = 0, completed = false;
  const answers = Object.create(null), skipped = new Set();
  function currentValue() { return String(answers[questions[index].id] || '').trim(); }
  function setValue(value) { answers[questions[index].id] = String(value || '').slice(0, 4000); skipped.delete(questions[index].id); status.textContent = ''; }
  function renderQuestion() {
    const question = questions[index];
    progress.textContent = 'السؤال ' + (index + 1) + ' من ' + questions.length;
    prompt.textContent = question.prompt;
    fields.replaceChildren(); status.textContent = '';
    if (question.type === 'single') {
      const optionsBox = document.createElement('div'); optionsBox.className = 'alpha-question-options';
      question.options.forEach((value, optionIndex) => {
        const label = document.createElement('label'); label.className = 'alpha-question-option';
        const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'alpha-question-' + Math.random().toString(36).slice(2); radio.value = value; radio.checked = currentValue() === value;
        radio.addEventListener('change', () => { setValue(value); custom.value = ''; });
        const text = document.createElement('span'); text.textContent = value; label.append(radio, text); optionsBox.appendChild(label);
      });
      const custom = document.createElement('textarea'); custom.className = 'alpha-question-custom'; custom.rows = 2; custom.maxLength = 4000;
      custom.placeholder = question.placeholder || 'أو اكتب إجابتك الخاصة هنا...';
      if (!question.options.includes(currentValue())) custom.value = currentValue();
      custom.addEventListener('input', () => {
        setValue(custom.value);
        optionsBox.querySelectorAll('input').forEach(radio => { radio.checked = false; });
      });
      fields.append(optionsBox, custom);
    } else {
      const input = document.createElement('textarea'); input.className = 'alpha-question-text'; input.rows = 3; input.maxLength = 4000;
      input.placeholder = question.placeholder || 'اكتب إجابتك...'; input.value = currentValue();
      input.addEventListener('input', () => setValue(input.value));
      fields.appendChild(input);
    }
    skip.disabled = completed; next.hidden = index >= questions.length - 1; submit.hidden = index < questions.length - 1;
    next.disabled = completed; submit.disabled = completed;
  }
  function recordCurrentAsSkipped() { skipped.add(questions[index].id); delete answers[questions[index].id]; }
  function proceed(skipCurrent) {
    const question = questions[index];
    if (skipCurrent) recordCurrentAsSkipped();
    else if (question.required && !currentValue()) { status.textContent = 'اختر إجابة أو اكتب إجابتك، أو اضغط تخطي.'; return; }
    if (index < questions.length - 1) { index += 1; renderQuestion(); }
  }
  skip.addEventListener('click', () => proceed(true));
  next.addEventListener('click', () => proceed(false));
  submit.addEventListener('click', () => {
    const current = questions[index];
    if (current.required && !currentValue() && !skipped.has(current.id)) { status.textContent = 'أجب عن السؤال أو اضغط تخطي قبل الإرسال.'; return; }
    const missing = questions.some(item => item.required && !String(answers[item.id] || '').trim() && !skipped.has(item.id));
    if (missing) { status.textContent = 'هناك سؤال مطلوب لم تتم الإجابة عنه؛ ارجع إليه أو تخطّه.'; return; }
    completed = true;
    const lines = questions.map((item, i) => (i + 1) + '. ' + item.prompt + '\nالإجابة: ' + (skipped.has(item.id) ? 'تم التخطي' : String(answers[item.id] || '').trim()));
    const submission = 'إجابات النموذج التفاعلي:\n' + lines.join('\n\n') + '\n\nتابع العمل بناءً على هذه الإجابات.';
    status.textContent = 'تم إرسال الإجابات إلى Alpha.';
    skip.disabled = next.disabled = submit.disabled = true;
    const text = document.createElement('div'); text.className = 'alpha-question-intro'; text.textContent = 'اكتملت الأسئلة وأُرسلت الإجابات.'; fields.replaceChildren(text);
    el('prompt').value = submission;
    el('prompt').style.height = 'auto'; el('prompt').style.height = Math.min(el('prompt').scrollHeight, 180) + 'px';
    sendMsg();
  });
  renderQuestion(); parent.appendChild(card); return true;
}

'''
s = s.replace(anchor, interactive_js + anchor, 1)

# Add Save to Workspace button to code-file action list.
anchor = """  const copyCode = document.createElement('button'); copyCode.type='button'; copyCode.className='code-action copy-code'; copyCode.title='نسخ الكود'; copyCode.setAttribute('aria-label','نسخ الكود');
  copyCode.appendChild(svgIcon('<path d=\"M8 8V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-3\"/><rect x=\"3\" y=\"8\" width=\"12\" height=\"13\" rx=\"2\"/><path d=\"M7 12h4M7 16h4\"/>'));
  copyCode.addEventListener('click',()=>copyText(code));
  actions.append(download, copyCode, previewToggle); head.append(identity, actions); card.append(head, preview);
"""
assert anchor in s
replacement = anchor.replace("  actions.append(download, copyCode, previewToggle); head.append(identity, actions); card.append(head, preview);\n", """  const saveWorkspace = document.createElement('button'); saveWorkspace.type='button'; saveWorkspace.className='code-action copy-code'; saveWorkspace.title='حفظ في Workspace'; saveWorkspace.setAttribute('aria-label','حفظ ' + filename + ' في Workspace');
  saveWorkspace.textContent = '＋ Workspace';
  saveWorkspace.addEventListener('click', async () => {
    saveWorkspace.disabled = true;
    try { await saveWorkspaceCodeFile(filename, code); saveWorkspace.textContent = '✓ محفوظ'; }
    catch (error) { saveWorkspace.textContent = 'تعذر الحفظ'; el('status').textContent = error.message || 'تعذر حفظ الملف في Workspace.'; }
    finally { saveWorkspace.disabled = false; }
  });
  actions.append(download, copyCode, saveWorkspace, previewToggle); head.append(identity, actions); card.append(head, preview);
""")
s = s.replace(anchor, replacement, 1)

# Add interactive capability after prompt construction in chat route.
anchor = '''    prompt = build_effective_system_prompt(
        get_model_prompt(model), unlazy_enabled, coding_tools,
        structured_mode=bool(unlazy_enabled or coding_tools),
    )
'''
assert anchor in s
s = s.replace(anchor, anchor + '    prompt += "\\n\\n" + CHAT_INTERACTIVE_QUESTIONS_INSTRUCTION\n', 1)

# Add workspace JS before function loadHistory, plus listeners.
anchor = 'async function loadHistory() {\n'
assert anchor in s
workspace_js = r'''let chatWorkspaceFiles = [];
let chatWorkspaceSelectedId = null;
function workspaceConversationParams() { return '?conversation_id=' + encodeURIComponent(currentConversationId); }
function setWorkspaceStatus(message, isError=false) {
  const status = el('workspaceStatus'); if (!status) return;
  status.textContent = message || ''; status.style.color = isError ? '#ffabb5' : '#879bb0';
}
function renderWorkspaceFileList() {
  const select = el('workspaceFileSelect'); if (!select) return;
  const previous = chatWorkspaceSelectedId;
  select.replaceChildren();
  const blank = document.createElement('option'); blank.value = ''; blank.textContent = 'إنشاء ملف جديد'; select.appendChild(blank);
  chatWorkspaceFiles.forEach(item => {
    const option = document.createElement('option'); option.value = item.id;
    option.textContent = item.filename + ' · ' + Number(item.size || 0).toLocaleString() + ' بايت'; select.appendChild(option);
  });
  const selected = chatWorkspaceFiles.find(item => item.id === previous);
  select.value = selected ? selected.id : '';
  chatWorkspaceSelectedId = selected ? selected.id : null;
  const hasSelection = Boolean(chatWorkspaceSelectedId);
  el('workspaceSave').disabled = !hasSelection;
  el('workspaceDownload').disabled = !hasSelection;
  el('workspaceDelete').disabled = !hasSelection;
}
async function loadWorkspaceFiles(selectId=null) {
  setWorkspaceStatus('جارٍ تحميل ملفات مساحة العمل...');
  try {
    const response = await fetch('/api/chat-workspace' + workspaceConversationParams(), {headers:{'Accept':'application/json'}, cache:'no-store'});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'تعذر تحميل Workspace.');
    chatWorkspaceFiles = Array.isArray(data.files) ? data.files : [];
    if (selectId) chatWorkspaceSelectedId = selectId;
    renderWorkspaceFileList();
    if (chatWorkspaceSelectedId) await loadWorkspaceFile(chatWorkspaceSelectedId);
    else { el('workspaceFilename').value = ''; el('workspaceContent').value = ''; }
    setWorkspaceStatus(chatWorkspaceFiles.length + ' ملف محفوظ في هذه المحادثة.');
  } catch (error) { setWorkspaceStatus(error.message || 'تعذر تحميل Workspace.', true); }
}
async function loadWorkspaceFile(fileId) {
  if (!fileId) return;
  try {
    const response = await fetch('/api/chat-workspace/' + encodeURIComponent(fileId) + workspaceConversationParams(), {headers:{'Accept':'application/json'}, cache:'no-store'});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'تعذر فتح الملف.');
    chatWorkspaceSelectedId = data.file.id;
    el('workspaceFilename').value = data.file.filename;
    el('workspaceContent').value = data.file.content || '';
    renderWorkspaceFileList();
    el('workspaceFileSelect').value = chatWorkspaceSelectedId;
  } catch (error) { setWorkspaceStatus(error.message || 'تعذر فتح الملف.', true); }
}
async function postWorkspaceFile(filename, content, fileId=null) {
  const response = await fetch('/api/chat-workspace', {
    method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'},
    body:JSON.stringify({conversation_id:currentConversationId, filename, content, file_id:fileId})
  });
  const data = await response.json(); if (!response.ok) throw new Error(data.error || 'تعذر حفظ الملف.');
  chatWorkspaceSelectedId = data.file.id;
  await loadWorkspaceFiles(chatWorkspaceSelectedId);
  setWorkspaceStatus('تم حفظ ' + data.file.filename + ' في Workspace.');
  return data.file;
}
async function saveWorkspaceCodeFile(filename, content) {
  const existing = chatWorkspaceFiles.find(item => item.filename === filename);
  let fileId = null;
  if (existing) {
    if (!window.confirm('يوجد ملف بهذا الاسم في Workspace. هل تريد استبدال محتواه؟')) throw new Error('تم إلغاء الحفظ؛ الملف الموجود لم يتغير.');
    fileId = existing.id;
  }
  if (!el('chatWorkspace').hidden) return postWorkspaceFile(filename, content, fileId);
  const response = await fetch('/api/chat-workspace', {
    method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'},
    body:JSON.stringify({conversation_id:currentConversationId, filename, content, file_id:fileId})
  });
  const data = await response.json(); if (!response.ok) throw new Error(data.error || 'تعذر حفظ الملف.');
  return data.file;
}
el('workspaceBtn').addEventListener('click', async () => {
  const panel = el('chatWorkspace'); const open = panel.hidden;
  panel.hidden = !open; el('workspaceBtn').classList.toggle('active', open); el('workspaceBtn').setAttribute('aria-expanded', String(open));
  if (open) await loadWorkspaceFiles();
});
el('workspaceClose').addEventListener('click', () => { el('chatWorkspace').hidden = true; el('workspaceBtn').classList.remove('active'); el('workspaceBtn').setAttribute('aria-expanded','false'); });
el('workspaceRefresh').addEventListener('click', () => loadWorkspaceFiles(chatWorkspaceSelectedId));
el('workspaceFileSelect').addEventListener('change', async () => {
  const id = el('workspaceFileSelect').value; chatWorkspaceSelectedId = id || null;
  if (id) await loadWorkspaceFile(id);
  else { el('workspaceFilename').value = ''; el('workspaceContent').value = ''; renderWorkspaceFileList(); setWorkspaceStatus('جاهز لإنشاء ملف جديد.'); }
});
el('workspaceCreate').addEventListener('click', async () => {
  try { await postWorkspaceFile(el('workspaceFilename').value, el('workspaceContent').value, null); }
  catch (error) { setWorkspaceStatus(error.message || 'تعذر إنشاء الملف.', true); }
});
el('workspaceSave').addEventListener('click', async () => {
  if (!chatWorkspaceSelectedId) return;
  try { await postWorkspaceFile(el('workspaceFilename').value, el('workspaceContent').value, chatWorkspaceSelectedId); }
  catch (error) { setWorkspaceStatus(error.message || 'تعذر حفظ التعديلات.', true); }
});
el('workspaceDelete').addEventListener('click', async () => {
  if (!chatWorkspaceSelectedId || !window.confirm('هل تريد حذف هذا الملف من Workspace؟')) return;
  try {
    const response = await fetch('/api/chat-workspace/' + encodeURIComponent(chatWorkspaceSelectedId) + workspaceConversationParams(), {method:'DELETE', headers:{'Accept':'application/json'}});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'تعذر حذف الملف.');
    chatWorkspaceSelectedId = null; await loadWorkspaceFiles(); setWorkspaceStatus('تم حذف الملف.');
  } catch (error) { setWorkspaceStatus(error.message || 'تعذر حذف الملف.', true); }
});
el('workspaceDownload').addEventListener('click', () => {
  if (!chatWorkspaceSelectedId) return;
  window.open('/api/chat-workspace/' + encodeURIComponent(chatWorkspaceSelectedId) + '/download' + workspaceConversationParams(), '_blank', 'noopener');
});

'''
s = s.replace(anchor, workspace_js + anchor, 1)

# On conversation changes, when open workspace refresh its data. Find explicit conversation-open code anchor.
anchor = """  historyLoadPromise=loadHistory(); await historyLoadPromise;
  closeChatMenu(); el('status').textContent='تم فتح المحادثة.'; refreshConversationList(el('historySearch').value.trim());
"""
if anchor in s:
    s = s.replace(anchor, """  historyLoadPromise=loadHistory(); await historyLoadPromise;
  if (!el('chatWorkspace').hidden) await loadWorkspaceFiles();
  closeChatMenu(); el('status').textContent='تم فتح المحادثة.'; refreshConversationList(el('historySearch').value.trim());
""", 1)

# When starting new chat close and reset workspace.
anchor = """  currentConversationId = createConversationId();
  persistActiveConversation();
"""
assert anchor in s
s = s.replace(anchor, """  currentConversationId = createConversationId();
  persistActiveConversation();
  chatWorkspaceSelectedId = null; chatWorkspaceFiles = [];
  if (el('chatWorkspace')) { el('chatWorkspace').hidden = true; el('workspaceBtn').classList.remove('active'); el('workspaceBtn').setAttribute('aria-expanded','false'); }
""", 1)

# Backend routes inserted before /chat
anchor = '@app.post("/chat")\n@login_required\ndef chat():\n'
assert anchor in s
routes = r'''@app.get("/api/chat-workspace")
@login_required
def api_chat_workspace_list():
    user = current_user()
    if user["role"] != "user":
        return jsonify(error="مساحة الملفات مخصصة لحساب المستخدم."), 403
    try:
        conversation_id = normalize_conversation_id(request.args.get("conversation_id", "default"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    with connect_db() as conn:
        rows = conn.execute(
            """SELECT id, filename, LENGTH(content) AS size, created_at, updated_at
               FROM chat_workspace_files WHERE user_id=? AND conversation_id=?
               ORDER BY updated_at DESC, filename COLLATE NOCASE LIMIT ?""",
            (user["id"], conversation_id, MAX_WORKSPACE_FILES),
        ).fetchall()
    return jsonify(files=[dict(row) for row in rows], max_files=MAX_WORKSPACE_FILES,
                   max_file_bytes=MAX_WORKSPACE_FILE_BYTES)


@app.get("/api/chat-workspace/<file_id>")
@login_required
def api_chat_workspace_get(file_id):
    user = current_user()
    if user["role"] != "user":
        return jsonify(error="مساحة الملفات مخصصة لحساب المستخدم."), 403
    try:
        conversation_id = normalize_conversation_id(request.args.get("conversation_id", "default"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not re.fullmatch(r"[a-f0-9-]{36}", str(file_id or "")):
        return jsonify(error="معرّف الملف غير صالح."), 400
    with connect_db() as conn:
        row = conn.execute(
            "SELECT id,filename,content,created_at,updated_at FROM chat_workspace_files WHERE id=? AND user_id=? AND conversation_id=?",
            (file_id, user["id"], conversation_id),
        ).fetchone()
    if row is None:
        return jsonify(error="لم يتم العثور على الملف ضمن Workspace هذه المحادثة."), 404
    return jsonify(file=dict(row))


@app.post("/api/chat-workspace")
@login_required
def api_chat_workspace_save():
    user = current_user()
    if user["role"] != "user":
        return jsonify(error="مساحة الملفات مخصصة لحساب المستخدم."), 403
    data = request.get_json(silent=True) or {}
    try:
        conversation_id = normalize_conversation_id(data.get("conversation_id", "default"))
        filename = normalize_workspace_filename(data.get("filename"))
        content = normalize_workspace_content(data.get("content"))
    except (ValueError, WorkspaceValidationError) as exc:
        return jsonify(error=str(exc)), 400
    file_id = data.get("file_id")
    if file_id not in (None, "") and not re.fullmatch(r"[a-f0-9-]{36}", str(file_id)):
        return jsonify(error="معرّف الملف غير صالح."), 400
    content_bytes = len(content.encode("utf-8"))
    with connect_db() as conn:
        if file_id:
            existing = conn.execute(
                "SELECT id, filename FROM chat_workspace_files WHERE id=? AND user_id=? AND conversation_id=?",
                (file_id, user["id"], conversation_id),
            ).fetchone()
            if existing is None:
                return jsonify(error="الملف المطلوب تعديله غير موجود في هذه المحادثة."), 404
        else:
            existing = None
        duplicate = conn.execute(
            "SELECT id FROM chat_workspace_files WHERE user_id=? AND conversation_id=? AND filename=? AND id<>?",
            (user["id"], conversation_id, filename, file_id or ""),
        ).fetchone()
        if duplicate:
            return jsonify(error="يوجد ملف آخر بالاسم نفسه. اختره من القائمة لحفظ تعديلاته أو غيّر الاسم."), 409
        rows = conn.execute(
            "SELECT id, content FROM chat_workspace_files WHERE user_id=? AND conversation_id=?",
            (user["id"], conversation_id),
        ).fetchall()
        total_bytes = sum(len(str(row["content"] or "").encode("utf-8")) for row in rows)
        file_count = len(rows)
        old_bytes = len(str(next((row["content"] for row in rows if file_id and row["id"] == file_id), "") or "").encode("utf-8")) if file_id else 0
        if not file_id and file_count >= MAX_WORKSPACE_FILES:
            return jsonify(error=f"وصلت إلى الحد الأقصى: {MAX_WORKSPACE_FILES} ملفاً لكل محادثة."), 413
        if total_bytes - old_bytes + content_bytes > MAX_WORKSPACE_TOTAL_BYTES:
            return jsonify(error="إجمالي مساحة الملفات في هذه المحادثة يتجاوز 20 ميغابايت."), 413
        if file_id:
            conn.execute(
                "UPDATE chat_workspace_files SET filename=?, content=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND conversation_id=?",
                (filename, content, file_id, user["id"], conversation_id),
            )
            saved_id = file_id
        else:
            saved_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO chat_workspace_files(id,user_id,conversation_id,filename,content) VALUES(?,?,?,?,?)",
                (saved_id, user["id"], conversation_id, filename, content),
            )
        saved = conn.execute(
            "SELECT id,filename,LENGTH(content) AS size,created_at,updated_at FROM chat_workspace_files WHERE id=? AND user_id=?",
            (saved_id, user["id"]),
        ).fetchone()
    return jsonify(file=dict(saved), message="تم حفظ الملف."), 200 if file_id else 201


@app.delete("/api/chat-workspace/<file_id>")
@login_required
def api_chat_workspace_delete(file_id):
    user = current_user()
    if user["role"] != "user":
        return jsonify(error="مساحة الملفات مخصصة لحساب المستخدم."), 403
    try:
        conversation_id = normalize_conversation_id(request.args.get("conversation_id", "default"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not re.fullmatch(r"[a-f0-9-]{36}", str(file_id or "")):
        return jsonify(error="معرّف الملف غير صالح."), 400
    with connect_db() as conn:
        cursor = conn.execute(
            "DELETE FROM chat_workspace_files WHERE id=? AND user_id=? AND conversation_id=?",
            (file_id, user["id"], conversation_id),
        )
        deleted = cursor.rowcount
    if not deleted:
        return jsonify(error="لم يتم العثور على الملف ضمن Workspace هذه المحادثة."), 404
    return jsonify(deleted=True)


@app.get("/api/chat-workspace/<file_id>/download")
@login_required
def api_chat_workspace_download(file_id):
    user = current_user()
    if user["role"] != "user":
        return jsonify(error="مساحة الملفات مخصصة لحساب المستخدم."), 403
    try:
        conversation_id = normalize_conversation_id(request.args.get("conversation_id", "default"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if not re.fullmatch(r"[a-f0-9-]{36}", str(file_id or "")):
        return jsonify(error="معرّف الملف غير صالح."), 400
    with connect_db() as conn:
        row = conn.execute(
            "SELECT filename,content FROM chat_workspace_files WHERE id=? AND user_id=? AND conversation_id=?",
            (file_id, user["id"], conversation_id),
        ).fetchone()
    if row is None:
        return jsonify(error="لم يتم العثور على الملف ضمن Workspace هذه المحادثة."), 404
    payload = str(row["content"] or "").encode("utf-8")
    return send_file(BytesIO(payload), mimetype="text/plain; charset=utf-8", as_attachment=True,
                     download_name=Path(row["filename"]).name, max_age=0)


'''
s = s.replace(anchor, routes + anchor, 1)

p.write_text(s, encoding='utf-8')
print('Patched', p, 'bytes=', p.stat().st_size)
