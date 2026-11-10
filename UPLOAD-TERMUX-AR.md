# رفع نسخة Alpha النهائية من Termux إلى GitHub ثم Render

هذا الدليل يرفع التعديلات فوق المستودع الحالي `zaidon4-bit/Alpha74748` ولا يحذف المستودع أو يستبدله. ملف ZIP يحتوي الملفات عند جذر المشروع مباشرة.

## 1. تنزيل الملف على الهاتف

نزّل `Alpha-Render-GitHub-Ready.zip` وضعه في مجلد Downloads. بعد ذلك افتح Termux.

## 2. تجهيز Termux

```bash
pkg update -y
pkg install git unzip python -y
termux-setup-storage
```

وافق على صلاحية الملفات في Android عند ظهور الطلب.

## 3. فتح المستودع الصحيح

إذا كان المستودع مستنسخاً سابقاً:

```bash
cd "$HOME/Alpha74748"
```

إذا لم يكن موجوداً:

```bash
cd "$HOME"
git clone https://github.com/zaidon4-bit/Alpha74748.git
cd "$HOME/Alpha74748"
```

تحقق من المستودع والفرع قبل المتابعة:

```bash
git remote -v
git branch --show-current
git status --short
```

يجب أن يشير `origin` إلى `zaidon4-bit/Alpha74748`. إذا كان مختلفاً، توقف ولا ترفع قبل التأكد من أنك داخل المستودع الصحيح.

إذا أظهر `git status --short` ملفات معدّلة أو غير متتبعة، لا تتابع مباشرة. احفظها أو اعمل نسخة احتياطية أولاً؛ لا تخلط تغييراتك السابقة مع هذه الحزمة دون مراجعتها.

## 4. سحب آخر نسخة قبل الدمج وأخذ نسخة احتياطية

```bash
BRANCH="$(git branch --show-current)"
git pull --ff-only origin "$BRANCH"
git archive --format=zip -o "$HOME/Alpha-before-render-supabase-integration.zip" HEAD
```

يحتفظ ملف النسخة الاحتياطية بالملفات المتتبعة في آخر commit. احتفظ أيضاً بنسخة مستقلة من أي ملفات محلية غير متتبعة تحتاجها.

## 5. فك الحزمة فوق المشروع

```bash
ls -lh "$HOME/storage/downloads/Alpha-Render-GitHub-Ready.zip"
unzip -t "$HOME/storage/downloads/Alpha-Render-GitHub-Ready.zip"
unzip -o "$HOME/storage/downloads/Alpha-Render-GitHub-Ready.zip" -d "$HOME/Alpha74748"
cd "$HOME/Alpha74748"
```

يستبدل `unzip -o` فقط الملفات التي تحمل الأسماء نفسها داخل الحزمة، ويضيف الملفات الجديدة. لا يحذف الملفات الأخرى الموجودة في المستودع.

## 6. فحص الملفات قبل الرفع

```bash
git diff --check
python -m py_compile app.py coding_workbench.py migrate_sqlite_to_supabase.py runtime_sandbox.py render_sandbox_probe.py supabase_live_check.py verify_alpha_deployment.py
```

تم تشغيل مجموعة الاختبارات الكاملة في بيئة Linux المستخدمة للتدقيق: `pytest -q` أعطى بعد تحديث تفعيل Sandbox عدد 126 اختباراً ناجحاً و25 حالة فرعية ناجحة، بما فيها اختبارات Render Sandbox الوهمية وفحص Supabase القراءة فقط. قد لا تدعم بيئة Termux/Android إنشاء Linux user namespaces وmount/chroot اللازمة لاختبارات Sandbox التكاملية؛ لا تعتبر فشل هذه الاختبارات على Android دليلاً على خلل في كود الاختبار أو نجاح بيئة Render. فحص التشغيل النهائي يجب أن يتم داخل بيئة استضافة Linux التي ستستخدمها.

## 7. إضافة الملفات التي راجعناها فقط إلى Git

استخدم القائمة الكاملة التالية، المطابقة لكل ملفات الحزمة (ولا تستخدم `git add -A`):

```bash
git add -- \
  .env.example \
  .gitignore \
  .python-version \
  ALPHA-AUDIT-FIXES-AR.txt \
  ALPHA-CHECKPOINT-CODE-FILES-UPDATE-AR.txt \
  ALPHA-FOUR-FEATURES-REPORT-AR.txt \
  ALPHA-XKIRO-SHARED-PROMPT-UPDATE-AR.txt \
  ALPHAX-INTEGRATION-NOTES.txt \
  AlphaX.html \
  CHECK-REPORT-AR.txt \
  DEEPSEEK-DEV-CODE-VERIFICATION-AR.txt \
  DEPLOY-RENDER-SUPABASE-AR.md \
  FINAL-AUDIT-AR.txt \
  LIVE-INTEGRATION-CHECKLIST-AR.md \
  LIVE-INTEGRATION-REPORT-AR.txt \
  PHASE-1-CHAT-TOOLS-REPORT-AR.txt \
  PHASE-1-REPORT-AR.txt \
  PHASE-2-PROJECT-INTELLIGENCE-TOOLS-REPORT-AR.txt \
  PHASE-2-REPORT-AR.txt \
  PHASE-2-VERIFICATION-AR.txt \
  PHASE-3-REPORT-AR.txt \
  PHASE-3-RUNTIME-REPORT-AR.txt \
  PHASE-5-REPORT-AR.txt \
  PHASE-6-NETWORK-REPORT-AR.txt \
  PROJECT-INTELLIGENCE-UI-UPDATE-AR.txt \
  Procfile \
  README-ar.txt \
  SANDBOX-ENABLEMENT-UPDATE-AR.md \
  UPLOAD-TERMUX-AR.md \
  alpha_workspace.py \
  app.py \
  apply_phase1.py \
  chat_workspace.py \
  checkpoint_store.py \
  coding_workbench.py \
  migrate_sqlite_to_supabase.py \
  project_intelligence.py \
  project_toolbox.py \
  render.yaml \
  render_sandbox_probe.py \
  requirements.txt \
  runtime_sandbox.py \
  secret_crypto.py \
  skills/unlazy/SKILL.md \
  supabase_live_check.py \
  test_chat_workspace.py \
  tests/test_alpha_ui_contracts.py \
  tests/test_alpha_workspace.py \
  tests/test_checkpoint_store.py \
  tests/test_coding_workbench.py \
  tests/test_migrate_sqlite_to_supabase.py \
  tests/test_project_apply_files.py \
  tests/test_project_intelligence.py \
  tests/test_project_toolbox.py \
  tests/test_qwen_fallback.py \
  tests/test_render_sandbox_adapter.py \
  tests/test_render_sandbox_probe.py \
  tests/test_runtime_sandbox.py \
  tests/test_secret_crypto.py \
  tests/test_sandbox_deployment_config.py \
  tests/test_supabase_live_check.py \
  verify_alpha_deployment.py
```

راجع ما سيتم رفعه:

```bash
git status --short
git diff --cached --stat
git diff --cached --check
```

لا تتابع إذا ظهر `app.db` أو `.api_encryption.key` أو `.flask_secret_key` أو `.env` أو أي ملف يحتوي مفتاح API. لا ترفع هذه الملفات إطلاقاً.

## 8. إنشاء Commit ورفعه

```bash
git commit -m "Integrate Render Sandboxes and verify Supabase deployment"
git push -u origin "$BRANCH"
```

إذا طلب GitHub تسجيل الدخول، استخدم وسيلة المصادقة التي يتيحها Git/Android. لا تضع Personal Access Token داخل الأوامر أو داخل ملفات المشروع أو المحادثة.

## 9. متابعة Render دون إنشاء خدمة مكررة

1. افتح Render Dashboard وافتح خدمة Alpha الحالية، وتأكد أن Repository هو `zaidon4-bit/Alpha74748` وأن Branch هو نفس الفرع الذي دفعته.
2. لا تضغط New Blueprint لإنشاء خدمة ثانية لمجرد رؤية `render.yaml`. هذا الملف يسمي الخدمة `alpha-ai`، بينما قد تكون الخدمة الحالية باسم `AAlphaX`. استخدم الخدمة الحالية إذا كانت مرتبطة بالمستودع الصحيح.
3. إذا كان Auto Deploy مفعلاً، ستبدأ عملية النشر بعد `git push`. وإلا استخدم Manual Deploy → Deploy latest commit من الخدمة الحالية.
4. راقب Build Logs. أمر البناء المحدد هو:

```bash
pip install --upgrade pip && pip install -r requirements.txt
```

وأمر التشغيل يجب أن يبقى عاملاً واحداً في الوقت الحالي:

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180 --access-logfile - --error-logfile - app:app
```

5. تأكد من متغيرات البيئة في الخدمة الحالية: `DATABASE_URL` (Supabase Shared Pooler Transaction mode على 6543) و`ADMIN_USERNAME` و`ADMIN_PASSWORD` و`FLASK_SECRET_KEY` و`API_ENCRYPTION_KEY` و`APP_ENV=production` و`COOKIE_SECURE=1`. أضف `ALPHA_RUNTIME_BACKEND=render` و`RENDER_API_KEY` و`RENDER_WORKSPACE_ID`، واختياريّاً `RENDER_SANDBOX_GROUP_ID`. اضبط `ALPHA_SANDBOX_ENABLED=1`؛ وهي القيمة الافتراضية في `render.yaml`. إذا كانت الخدمة موجودة مسبقاً، تحقق من القيمة يدوياً في Render Dashboard → Environment. لا تغيّر `FLASK_SECRET_KEY` أو `API_ENCRYPTION_KEY` عشوائياً في خدمة قائمة؛ قد يؤدي ذلك إلى فقدان الجلسات أو عدم القدرة على فك مفاتيح API القديمة.
6. بعد اكتمال النشر افتح `https://YOUR-SERVICE.onrender.com/healthz`. يجب أن يعيد HTTP 200 وJSON بحالة `ok`.
7. سجّل الدخول، ثم اختبر إنشاء حساب تجريبي، محادثة جديدة، سجل محادثة قديم، أدوات الأسئلة التفاعلية، إنشاء/تعديل/تنزيل Workspace، Project Intelligence، Apply Patch على ZIP تجريبي، Checkpoint وRestore، وذاكرة مشروع منفصل.
8. افتح `/api/project-runtime/status` بعد تسجيل الدخول. يجب أن يظهر `provider=render-sandboxes` و`enabled=true` و`ready=true` بعد إضافة بيانات الاعتماد والتحقق من اتصال Render. مزود Render Sandboxes يستخدم العزل المدار منفصلاً عن Web Service، وليس Linux namespaces/chroot داخل خادم Flask. إن لم يظهر `ready=true`، افحص `missing` و`probe_detail` وسجلات Render؛ لا يوجد fallback ينفذ كود المستخدم داخل Flask.

## 10. ترحيل بيانات SQLite القديمة إلى Supabase (اختياري)

لا تحتاج هذه الخطوة إذا كانت بياناتك موجودة بالفعل في Supabase أو لا تريد نقل قاعدة Termux القديمة.

1. خذ نسخة احتياطية من `app.db` و`.api_encryption.key` و`.flask_secret_key` واحتفظ بها خارج مجلد Git.
2. أنشئ Supabase PostgreSQL واربطه بخدمة Render. انشر التطبيق أولاً لكي ينشئ مخططات المستخدمين والمحادثات وإعدادات النماذج في قاعدة الهدف.
3. إذا أردت نقل مفاتيح API المشفرة القديمة، اجعل `API_ENCRYPTION_KEY` في Render مطابقاً تماماً لمحتوى `.api_encryption.key` القديم قبل أن يعتمد التطبيق على القاعدة المنقولة. لا ترفع ملف المفتاح ولا تضع قيمته في GitHub.
4. تأكد أن قاعدة الهدف لم تحفظ فيها أي رسائل محادثة بعد؛ أداة الترحيل تتوقف إذا وجدت رسائل موجودة حتى لا تكرر السجل. لا تشغّلها على قاعدة مستخدمة من دون خطة ترحيل مخصصة.
5. انسخ نسخة `app.db` إلى مجلد المشروع المحلي في Termux (المجلد نفسه الذي يحتوي `migrate_sqlite_to_supabase.py`)، ولا تضفها إلى Git.
6. ثبّت مكتبة PostgreSQL المطلوبة محلياً ثم أدخل رابط Supabase عبر مطالبة مخفية:

```bash
python -m pip install 'psycopg[binary]>=3.2,<4'
read -rsp "Supabase DATABASE_URL: " DATABASE_URL
printf '\n'
export DATABASE_URL
python migrate_sqlite_to_supabase.py --source app.db
unset DATABASE_URL
```

7. راجع أعداد `users` و`messages` و`workspace_files` و`project_checkpoints` و`project_memories` التي تطبعها الأداة. احتفظ بنسخة SQLite الأصلية حتى تتحقق من السجلات والملفات داخل الموقع المنشور.

تنبيه: اختبارات `pytest` المحلية لا تعمل داخل Sandbox المستخدم، واختبارات Render الوهمية لا تنشئ موارد على حسابك. سكربت `render_sandbox_probe.py` وحده ينشئ Sandbox حية مؤقتة لفحص الاتصال والملفات والشبكة ثم ينهيها، وقد يستهلك موارد. اختبارات الترحيل تستخدم PostgreSQL mock ولا تتصل بمشروع Supabase الحقيقي؛ شغّل `supabase_live_check.py` أو افحص `/healthz` لإجراء التحقق الحي. نفّذ الترحيل مرة واحدة فقط على قاعدة هدف نظيفة من الرسائل.

## ما لا تفعله

- لا تحذف المستودع القديم ولا تستبدل تاريخه.
- لا ترفع قاعدة بيانات أو مفاتيح أو `.env`.
- لا تستخدم `git add -A` في الرفع الأول.
- لا تنشئ Render Blueprint جديداً قبل التأكد أن الخدمة الحالية غير مرتبطة بالمستودع.
- تفعيل Sandbox في `render.yaml` لا يعني أن حساب Render تم اختباره حياً؛ أضف بيانات الاعتماد وتحقق من `/api/project-runtime/status` قبل أول جلسة فعلية. لا تشغّل كود المستخدم داخل Flask كبديل عند فشل الموصل.
