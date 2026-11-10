# فحص التكامل الحي لـ Alpha — Render + Supabase + Render Sandboxes

هذا الدليل يفصل ما يمكن فحصه من Termux أو Render Dashboard بعد رفع المشروع. لا ترسل كلمات المرور أو مفاتيح API أو `DATABASE_URL` إلى المحادثة، ولا تضعها في GitHub.

## الحالة قبل الرفع

- موصل Render Sandboxes الرسمي مضاف إلى `runtime_sandbox.py` باستخدام `render>=1.8.0`.
- `render.yaml` يضبط `ALPHA_RUNTIME_BACKEND=render` و`ALPHA_SANDBOX_ENABLED=1`؛ الميزة مفعّلة افتراضياً في إعداد النشر.
- Sandbox تنشأ مع `network_policy=deny-all` ولا تتلقى `DATABASE_URL` أو أسرار Flask أو مفاتيح مزودي النماذج.
- أداة `supabase_live_check.py` تقرأ `DATABASE_URL` من البيئة فقط، تنفذ `SELECT 1` وتتحقق من جداول Alpha الأساسية دون قراءة محتوى المستخدمين أو تغيير البيانات.
- لا يمكن لهذه الحزمة أن تتصل بحساب Render أو Supabase دون بيانات اعتماد المالك. لا تعتبر الاختبارات الوهمية بديلاً عن الاختبار الحي.

## A. رفع المشروع ونشر Flask/Gunicorn

1. ارفع الملفات إلى المستودع الحالي `zaidon4-bit/Alpha74748` مع الاحتفاظ بقاعدة البيانات والمفاتيح خارج Git.
2. في Render افتح خدمة Alpha الحالية المرتبطة بالمستودع نفسه. لا تنشئ خدمة ثانية إذا كانت الخدمة الحالية صحيحة.
3. Build Command:

   `pip install --upgrade pip && pip install -r requirements.txt`

4. Start Command:

   `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180 --access-logfile - --error-logfile - app:app`

5. احتفظ بمتغيرات الأسرار الحالية. أضف/تأكد من `DATABASE_URL`، `APP_ENV=production`، `COOKIE_SECURE=1`، `FLASK_SECRET_KEY` و`API_ENCRYPTION_KEY`. لا تستبدل مفاتيح قائمة عشوائياً.
6. اضبط `ALPHA_SANDBOX_ENABLED=1` بعد التأكد من إضافة بيانات اعتماد Render؛ هذه القيمة موجودة افتراضياً في `render.yaml`.
7. انتظر أن تصبح خدمة Render `Live`، وافتح `https://YOUR-SERVICE.onrender.com/healthz`. المطلوب HTTP 200 وJSON `{"status":"ok"}`. هذا المسار ينفذ `SELECT 1` من خلال اتصال التطبيق نفسه.

## B. فحص Supabase الحي

1. استخدم Supabase **Shared Pooler → Transaction mode** والمنفذ `6543` لخدمة Flask الحالية. لا تستخدم direct IPv6 connection على Render ما لم يكن إعداد IPv4 ملائماً. `connect_db()` وملف الفحص يعطلان إعداد prepared statements في psycopg.
2. افتح Render Shell لخدمة Alpha إن كانت متاحة في خطة حسابك، ثم شغّل:

   `python supabase_live_check.py`

   السكربت يستخدم `DATABASE_URL` الموجودة في بيئة الخدمة ولا يطبعها. النجاح المطلوب `ok: true` و`missing_tables: []`.
3. إن لم تتوفر Render Shell، شغّل من Termux بعد تثبيت الاعتماديات، وأدخل DSN بمطالبة مخفية:

   ```bash
   python -m pip install 'psycopg[binary]>=3.2,<4'
   read -rsp "Supabase DATABASE_URL: " DATABASE_URL
   printf '\n'
   export DATABASE_URL
   python supabase_live_check.py
   unset DATABASE_URL
   ```

4. إذا نجح `SELECT 1` وظهرت جداول مفقودة، أعد تشغيل خدمة Alpha مرة واحدة حتى يكمل التطبيق إنشاء المخطط، ثم أعد الفحص. لا تشغّل ترحيلاً لقاعدة مستخدمة من دون نسخة احتياطية وخطة ترحيل منفصلة.

الجداول التي يتأكد منها السكربت: `users`, `chat_messages`, `chat_workspace_files`, `project_checkpoints`, `alpha_project_memory`.

## C. تهيئة Render Sandboxes

1. تحقق من إتاحة Render Sandboxes لمساحة العمل. إنشاء Sandbox Group يدوياً اختياري؛ يمكن إنشاء مجموعة باسم `alpha-project-runtime` في Oregon من **New → Sandbox Group**. أو اترك Render ينشئ أول مجموعة افتراضية تلقائياً عند أول Sandbox. إذا لم يظهر خيار المجموعة أو فشل الاختبار بسبب عدم الإتاحة، اطلب تفعيل Render Sandboxes لمساحة العمل.
2. أنشئ Render API Key بصلاحيات إدارة Sandboxes المطلوبة، واستخرج Workspace ID من إعدادات مساحة العمل.
3. ضع في Environment لخدمة Alpha:
   - `ALPHA_RUNTIME_BACKEND=render`
   - `RENDER_API_KEY` = المفتاح السري.
   - `RENDER_WORKSPACE_ID` = Workspace ID.
   - `RENDER_SANDBOX_GROUP_ID` = Group ID (اختياري إذا كانت المجموعة الافتراضية صحيحة).
   - `RENDER_SANDBOX_PLAN=1c-2g`
   - `ALPHA_SANDBOX_ENABLED=1` لتفعيل المسار؛ لا يبدأ التنفيذ فعلياً ما لم تنجح تهيئة Render API.
4. أعد نشر خدمة Alpha، ثم سجّل الدخول وافتح `/api/project-runtime/status`. المطلوب `provider: render-sandboxes` و`enabled: true` و`missing: []` و`ready: true` بعد إعداد المتغيرات ونجاح اتصال Render API. هذا فحص حالة الموصل ولا ينشئ Sandbox بحد ذاته.

## D. اختبار Sandbox من Termux أو جهاز موثوق

هذا الاختبار ينشئ Sandbox مؤقتة، ويتحقق من غلاف timeout وPython وvenv وpip، وينقل ملفاً ذهاباً وإياباً، ويختبر منع الاتصال بعنوان خارجي، ثم يحاول إنهاء Sandbox. قد تُحتسب تكلفة استخدام Sandbox. لا تشارك المتغيرات أو مخرجاتها السرية.

```bash
python -m pip install 'render>=1.8.0'
read -rsp "Render API key: " RENDER_API_KEY
printf '\n'
export RENDER_API_KEY
read -rp "Render Workspace ID: " RENDER_WORKSPACE_ID
export RENDER_WORKSPACE_ID
python render_sandbox_probe.py
unset RENDER_API_KEY RENDER_WORKSPACE_ID
```

إذا كانت عندك مجموعة غير افتراضية، أضف `RENDER_SANDBOX_GROUP_ID` إلى البيئة قبل تنفيذ الاختبار. يجب أن تظهر جميع النتائج الأربع `PASS` (`command_timeout_wrapper`, `python_and_venv`, `file_transfer`, `network_denied`) و` sandbox_cleanup: PASS`. هذا الاختبار فحص تكامل حي اختياري للتحقق من الموصل، وليس مجموعة اختبارات التطبيق `pytest`، وقد يستهلك موارد مدفوعة.

بعد ضبط بيانات الاعتماد، سجّل الدخول إلى Alpha، وافتح Project Intelligence، وابدأ مساحة مشروع تجريبية غير حساسة. ستظهر موافقة صريحة قبل إرسال ملفاتك إلى Sandbox في Oregon. اختبر Python وShell وتصدير ZIP ثم أوقف الجلسة. إذا تعذر الاتصال أو فشل الفحص، سيبقى العلم مفعّلاً في الإعدادات لكن ستبقى `ready=false` ولن ينفذ التطبيق الكود داخل Flask كبديل.

## ما لم يُنفذ من جلسة تجهيز الملفات

- لم يُنفذ Deploy إلى Render؛ لا يوجد اتصال مصرح به إلى حسابك من هذه الجلسة.
- لم يتم اختبار DSN الخاص بمشروع Supabase؛ لم يكن `DATABASE_URL` متاحاً في بيئة العمل.
- لم يتم تشغيل Flask/Gunicorn كخادم حي هنا؛ `flask`, `gunicorn`, `psycopg`, و`render` غير مثبّتة في بيئة الفحص، ومحاولة تنزيلها فشلت بسبب منع اتصال DNS الخارجي. اجتياز `py_compile` واختبارات SDK الوهمية لا يثبت تشغيل HTTP.
- Render Sandboxes Public Beta؛ تعمل حالياً في Oregon، ولا تدعم بعد private networking إلى خدمات Render أو Databases. لذلك ملفات المشروع المرفقة تنتقل إلى Oregon بعد موافقة المستخدم، لكن أسرار التطبيق وبيانات قاعدة البيانات لا تنتقل إلى Sandbox.
- Sandbox sessions محفوظة في ذاكرة عامل Gunicorn الحالي؛ إعادة تشغيل خدمة الويب تفقد مرجع الجلسة في الواجهة، وقد تبقى Sandbox قائمة حتى انتهاء مهلة Render التي تم ضبطها على ساعة. أوقف الجلسة بعد الاختبار، ولا ترفع عدد عمال Gunicorn قبل توفير مخزن جلسات مشترك.

## مصادر الوثائق الرسمية

- Render Python SDK: https://render.com/docs/sandboxes-sdk-python
- Render Sandboxes: https://render.com/docs/sandboxes
- Render Flask deployment: https://render.com/docs/deploy-flask
- Render → Supabase Postgres: https://render.com/articles/how-to-connect-a-render-service-to-supabase-postgres
- Supabase database connections: https://supabase.com/docs/guides/database/connecting-to-postgres
