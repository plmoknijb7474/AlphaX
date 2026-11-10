# Alpha — Alpha 3.1 Max + Alpha 2.7 Flash

تطبيق دردشة Flask متعدد المستخدمين، مع مفاتيح API منفصلة لكل نموذج ولوحة تحكم مشرف. يدعم التشغيل المحلي والنشر على Railway مع PostgreSQL (Railway PostgreSQL أو Supabase).

## النماذج الظاهرة للمستخدم

1. **Alpha 3.1 Max** — الإصدار الأساسي مع مسار احتياطي تلقائي عند تعذر الاتصال.
2. **Alpha 2.7 Flash** — الإصدار السريع للمحادثات والمهام اليومية.

## المميزات المحفوظة

- لوحة مشرف ومستخدمون منفصلون، وتخصيص مفاتيح API لكل مستخدم.
- حتى 8 مفاتيح اتصال لكل نموذج بترتيب أولوية، وتحويل تلقائي للمسار الاحتياطي عند فشل الاتصال الحالي.
- System Prompt عام واحد يطبّق على جميع النماذج ومسارات AI Chat وProject Intelligence وDev Code والمراجعة والإصلاح واستدعاءات أدوات الذكاء الاصطناعي.
- الاستدلال في Alpha 3.1 Max تلقائي؛ إعداد التفكير اليدوي يبقى متاحاً لـ Alpha 2.7 Flash.
- مستويات التفكير لـ Alpha 2.7 Flash، وUNLAZY.
- مراجعة الكود وإصلاحه تلقائياً، Diff Viewer، والمرفقات والصور والملفات.
- ذاكرة محادثة مشتركة بين النموذجين لآخر 80 رسالة لكل مستخدم.
- أسئلة تفاعلية، Workspace لكل محادثة، ونقاط استعادة للمشاريع.
- أدوات Project Intelligence وCode Generation وCode Modification وCode Testing وREADME Generator وغيرها.
- بيئة تنفيذ مشاريع معزولة، متاحة من خلال خدمة Railway Runner خاصة؛ لا تعمل داخل عملية Flask.

## التشغيل المحلي

```bash
python -m pip install -r requirements.txt
cp .env.example .env
# عدّل ADMIN_PASSWORD وFLASK_SECRET_KEY وAPI_ENCRYPTION_KEY وDATABASE_URL عند الحاجة
set -a; . ./.env; set +a
python app.py
```

افتح `http://127.0.0.1:5000/login`. التشغيل المحلي يستخدم SQLite إذا لم تضبط `DATABASE_URL`. بيئة التنفيذ المحلية تبقى متوقفة حتى تضبط `ALPHA_SANDBOX_ENABLED=1` وينجح اختبار Linux namespaces وmount وchroot.

## النشر على Railway — الخدمة الرئيسية + خدمة Runner

راجع `DEPLOY-RAILWAY-SUPABASE-AR.md`؛ هذا هو الدليل الحالي للنشر. أنشئ خدمتين من المستودع نفسه داخل مشروع Railway نفسه والبيئة نفسها:

- `alpha` (الواجهة والخادم): يستخدم `Dockerfile`، ويكون لديه Public Domain.
- `alpha-runner` (التنفيذ المعزول): يستخدم `Dockerfile.runner`، ويعمل على منفذ `8080`، ولا تنشئ له Public Domain.

تتصل الخدمة الرئيسية بخدمة Runner عبر `http://alpha-runner.railway.internal:8080` باستخدام رمز مشترك `ALPHA_RUNNER_TOKEN`. لا يحتاج التطبيق إلى `RAILWAY_API_TOKEN` ولا إلى أي مفاتيح Render. لا تضف قاعدة البيانات أو مفاتيح AI أو `FLASK_SECRET_KEY` إلى خدمة Runner.

يجب أن تكون الخدمتان في المشروع والبيئة نفسيهما، وخدمة Runner بنسخة واحدة وGunicorn worker واحد لأن جلسات التنفيذ محفوظة في ذاكرة عملية Runner. يختبر Runner صلاحيات Linux user namespaces وmount وchroot عند قراءة حالته؛ إذا لم تسمح بيئة Railway بها، ستظهر `ready=false` ويُرفض تنفيذ كود المستخدم (fail-closed). لا نعتبر إعداد Sandbox ناجحاً حتى يظهر `ready=true` بعد النشر.

## متغيرات الخدمة الرئيسية

```env
APP_ENV=production
COOKIE_SECURE=1
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-secret>
DATABASE_URL=<PostgreSQL URL>
FLASK_SECRET_KEY=<long-random-secret>
API_ENCRYPTION_KEY=<existing-key-or-new-random-secret>
ALPHA_RUNTIME_BACKEND=railway
ALPHA_SANDBOX_ENABLED=1
ALPHA_RUNNER_URL=http://alpha-runner.railway.internal:8080
ALPHA_RUNNER_TOKEN=<same-random-token-as-runner>
```

## متغيرات خدمة alpha-runner فقط

```env
PORT=8080
ALPHA_RUNTIME_BACKEND=local
ALPHA_SANDBOX_ENABLED=1
ALPHA_RUNNER_TOKEN=<same-random-token-as-main-service>
```

لا تضف إلى Runner: `DATABASE_URL` أو `ADMIN_PASSWORD` أو `FLASK_SECRET_KEY` أو `API_ENCRYPTION_KEY` أو مفاتيح مزودي AI.

## قاعدة البيانات والتشفير

يستخدم التطبيق `DATABASE_URL`. يمكنك ربط متغير قاعدة Railway PostgreSQL أو وضع رابط Supabase PostgreSQL. لا ترفع `app.db` أو `.api_encryption.key` أو `.flask_secret_key` أو `.env` إلى GitHub.

عند نقل قاعدة قديمة تحتوي مفاتيح API مشفرة، استخدم القيمة الأصلية لملف `.api_encryption.key` كـ `API_ENCRYPTION_KEY`. لا تولّد مفتاحاً جديداً في هذه الحالة؛ وإلا لن يستطيع التطبيق فك تشفير المفاتيح المخزنة سابقاً. كذلك لا تغيّر `FLASK_SECRET_KEY` عشوائياً على خدمة قائمة.

## فحص النشر

- الواجهة: `/healthz` يتحقق من اتصال قاعدة البيانات.
- خدمة Runner داخلياً: `/internal/healthz` يفحص حياة الخدمة فقط.
- بعد تسجيل الدخول افتح `/api/project-runtime/status`. المطلوب `provider=railway-runner` و`enabled=true` و`ready=true` و`missing=[]`.
- `ready=false` يعني أن إعداد الرابط/الرمز ناقص أو أن نظام Linux لم يسمح بالعزل. لا تشغّل الكود داخل Flask كحل بديل.

## سياسة بيئة التنفيذ

كل جلسة تعمل في user, mount, PID, network, IPC وUTS namespaces وchroot داخل خدمة Runner، مع حدود ملفات وأوامر ومدة الجلسة ومنع اتصال الشبكة الصادر. تثبيت الحزم من ملفات Wheel محلية داخل `wheels/` أو `wheelhouse/` فقط. يتم نقل الملفات إلى خدمة Runner بعد موافقة المستخدم الظاهرة. لا ترفق أسراراً أو ملفات حساسة. جلسات Runner مؤقتة وقد تنتهي عند إعادة تشغيل الخدمة.

## الترحيل من SQLite إلى PostgreSQL

توجد أداة `migrate_sqlite_to_supabase.py` لنقل الحسابات والمحادثات وتعليمات النماذج ومفاتيح API المشفرة ومسارات API وملفات Workspace ونقاط استعادة المشاريع وذاكرة Project Intelligence. راجع دليل النشر قبل تنفيذ الترحيل، وخذ نسخة احتياطية أولاً.

**ملاحظة حول التقارير السابقة:** بعض تقارير المراحل والتدقيق القديمة تحتفظ بسجل تاريخي لإعداد الاستضافة السابق. لا تتبع منها أي خطوات نشر قديمة؛ الدليل التنفيذي الوحيد الحالي هو `DEPLOY-RAILWAY-SUPABASE-AR.md`، وإعداد الرفع من الهاتف في `UPLOAD-TERMUX-AR.md`.
