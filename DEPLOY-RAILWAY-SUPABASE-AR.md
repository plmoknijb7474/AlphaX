# دليل نشر Alpha على Railway من الصفر

هذا الدليل يستبدل تعليمات Render القديمة. النشر يتكوّن من خدمتين داخل مشروع Railway واحد وبيئة واحدة: خدمة ويب `alpha` وخدمة تنفيذ خاصة `alpha-runner`.

## 1) رفع المشروع إلى GitHub

ارفع محتويات هذه الحزمة إلى جذر المستودع، بحيث يكون `app.py` و`requirements.txt` و`Dockerfile` و`Dockerfile.runner` في الجذر. لا ترفع `.env` أو قواعد البيانات المحلية أو ملفات المفاتيح.

## 2) إنشاء مشروع وخدمة الويب

1. افتح Railway Dashboard وأنشئ Project جديداً.
2. اختر Deploy from GitHub Repo واربط المستودع `plmoknijb7474/AlphaX` والفرع `main`.
3. اترك Root Directory فارغاً.
4. سيتعرف Railway على `Dockerfile` الموجود في الجذر. لا تحتاج Build Command منفصلاً.
5. Start Command الافتراضي في Dockerfile يشغّل `gunicorn ... app:app`. إذا احتجت ضبطه يدوياً استخدم:

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180 --access-logfile - --error-logfile - app:app
```

6. اجعل Healthcheck Path هو `/healthz`.
7. من Settings → Networking → Public Networking أنشئ Domain لهذه الخدمة فقط.

## 3) إنشاء قاعدة البيانات

إما:
- إضافة PostgreSQL من Railway ثم تعيين `DATABASE_URL` إلى متغير قاعدة البيانات المرجعي من خدمة PostgreSQL، أو
- استخدام رابط PostgreSQL الحالي من Supabase في `DATABASE_URL`.

في الحالتين يجب أن تتصل خدمة الويب بقاعدة PostgreSQL قابلة للوصول. لا تستخدم SQLite مؤقتة في الإنتاج.

## 4) إنشاء خدمة Alpha Runner الخاصة

1. أضف خدمة جديدة داخل المشروع والبيئة نفسيهما.
2. اربط المستودع نفسه والفرع `main` نفسه.
3. اترك Root Directory فارغاً.
4. في Variables أضف `RAILWAY_DOCKERFILE_PATH` بالقيمة `Dockerfile.runner` حتى يستخدم Runner صورة أصغر تحتوي متطلبات التنفيذ فقط.
5. اضبط/أضف `PORT=8080`.
6. Start Command (إذا لم يأخذ CMD من Dockerfile):

```bash
gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --timeout 180 --access-logfile - --error-logfile - railway_runner:app
```

7. Healthcheck Path: `/internal/healthz`.
8. لا تنشئ Public Domain لهذه الخدمة. ستستخدم الواجهة اسمها الداخلي عبر Railway Private Networking.
9. اترك عدد النسخ Replicas = 1؛ جلسات التنفيذ تحفظها عملية Runner الواحدة في الذاكرة، ولا يوجد Redis لتنسيق جلسات متعددة النسخ.

اسم الخدمة مهم: `alpha-runner`. إذا اخترت اسماً آخر، يجب أن يتطابق المضيف داخل `ALPHA_RUNNER_URL` معه.

## 5) إنشاء رمز الاتصال الداخلي

أنشئ رمزاً عشوائياً طويلاً (48 حرفاً أو أكثر). يمكنك توليده من Termux:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

انسخ الرمز نفسه إلى `ALPHA_RUNNER_TOKEN` في خدمتي `alpha` و`alpha-runner`. لا ترسله في المحادثة ولا تحفظه في GitHub.

## 6) متغيرات خدمة alpha الرئيسية

أضف في خدمة الويب `alpha`:

| Key | Value |
|---|---|
| `APP_ENV` | `production` |
| `COOKIE_SECURE` | `1` |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | كلمة مرور قوية من اختيارك |
| `DATABASE_URL` | رابط Railway PostgreSQL أو Supabase PostgreSQL |
| `FLASK_SECRET_KEY` | سر عشوائي طويل ثابت لهذه الخدمة |
| `API_ENCRYPTION_KEY` | المفتاح القديم عند نقل قاعدة سابقة، أو سر عشوائي جديد عند البدء من الصفر |
| `ALPHA_RUNTIME_BACKEND` | `railway` |
| `ALPHA_SANDBOX_ENABLED` | `1` |
| `ALPHA_RUNNER_URL` | `http://alpha-runner.railway.internal:8080` |
| `ALPHA_RUNNER_TOKEN` | الرمز المشترك الذي أنشأته في الخطوة السابقة |

لا تضف `PORT` يدوياً لخدمة الويب؛ Railway يمرره للخدمة عند التشغيل.

## 7) متغيرات خدمة alpha-runner فقط

أضف في خدمة Runner:

| Key | Value |
|---|---|
| `PORT` | `8080` |
| `ALPHA_SANDBOX_ENABLED` | `1` |
| `ALPHA_RUNNER_TOKEN` | الرمز المشترك نفسه من خدمة الويب |
| `APP_ENV` | `production` |
| `ALPHA_RUNTIME_BACKEND` | `local` (المحرك الداخلي للـ Runner فقط) |

لا تضف إلى Runner: `DATABASE_URL` أو `ADMIN_PASSWORD` أو `FLASK_SECRET_KEY` أو `API_ENCRYPTION_KEY` أو أي مفاتيح لمزودي AI. لا يحتاج التطبيق إلى `RAILWAY_API_TOKEN` ولا إلى أي متغير يبدأ بـ `RENDER_`.

## 8) النشر والتحقق

1. انشر خدمتي `alpha` و`alpha-runner`.
2. انتظر نجاح Deploy لكل خدمة.
3. افتح نطاق خدمة الويب `/healthz`. يجب أن يظهر `{"status":"ok"}` بعد نجاح اتصال قاعدة البيانات.
4. سجّل الدخول كمشرف ثم افتح `/api/project-runtime/status` ضمن جلسة المستخدم المناسبة. يجب أن تكون النتيجة `provider=railway-runner`, `enabled=true`, `ready=true`, `missing=[]`.
5. إذا كانت `ready=false` فافحص `note` و`probe_detail` وسجلات خدمة Runner. من الأسباب المحتملة أن بيئة Railway لا تسمح بـ Linux user namespaces أو mount/chroot. في هذه الحالة يرفض Alpha التنفيذ عمداً؛ لا تغيّر الإعداد ليشغّل أوامر المستخدم داخل Flask.
6. بعد ظهور `ready=true` فقط، ابدأ جلسة تجريبية بمشروع غير حساس، وافق على نقل الملفات إلى Runner، جرّب `python main.py`، ثم نزّل ZIP وأوقف الجلسة.

## 9) حدود الأمان والتشغيل

- خدمة Runner منفصلة ولا تحصل على قاعدة البيانات أو أسرار AI أو مفاتيح تشفير Alpha.
- التواصل بين الخدمتين عبر HTTP الخاص على Railway Private Networking، مع Bearer token عشوائي مشترك. لا تنشئ نطاقاً عاماً لـ Runner.
- أوامر المشروع تعمل داخل Linux namespaces وchroot في Runner، مع سياسة شبكة معزولة. `ALPHA_SANDBOX_ENABLED=1` لا يكفي وحده؛ لا بد أن ينجح اختبار العزل الفعلي.
- لا يوجد اتصال إنترنت داخل مساحة التنفيذ. تثبيت الحزم مسموح من ملفات Wheel محلية فقط ضمن `wheels/` أو `wheelhouse/`.
- Runner عملية واحدة ونسخة واحدة لأن الجلسات والعمليات الفرعية في الذاكرة. إعادة تشغيل Runner تنهي الجلسات النشطة.
- ملفات المشروع المرفوعة ترسل إلى Runner بعد موافقة المستخدم. لا ترفق أسراراً أو ملفات بيانات اعتماد.
- هذا التنفيذ لا يستخدم Railway API لإنشاء خدمة منفصلة لكل مستخدم؛ بل خدمة Runner واحدة خاصة تفصل بيئة الكود عبر Linux namespaces. إذا منع Railway هذه الصلاحيات فميزة التنفيذ تبقى غير جاهزة وتُرفض بأمان.

## 10) مفاتيح التشفير وقاعدة قديمة

إذا كنت تنقل قاعدة بيانات قديمة، احتفظ بقيمة `.api_encryption.key` الأصلية وضعها في `API_ENCRYPTION_KEY`. لا تولّد مفتاحاً جديداً مع قاعدة قديمة تحتوي مفاتيح API مشفرة. احتفظ أيضاً بـ `FLASK_SECRET_KEY` القديم عند الحاجة للحفاظ على جلسات المستخدمين. خذ نسخة احتياطية قبل ترحيل SQLite إلى PostgreSQL.
