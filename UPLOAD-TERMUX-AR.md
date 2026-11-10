# تحديث مستودع AlphaX من Termux وبدء النشر على Railway

المستودع المعتمد: `https://github.com/plmoknijb7474/AlphaX.git` والفرع `main`.

## 1) تنزيل الحزمة

نزّل `AlphaX-Railway-Ready.zip` إلى مجلد Downloads في Android. افتح Termux ونفّذ:

```bash
pkg update -y && pkg install git unzip python openssl -y
termux-setup-storage
```

## 2) استنساخ المستودع في مجلد جديد

لا تستخدم المجلد القديم الذي قد يحتوي على Commit محلي غير مرفوع. أنشئ نسخة عمل جديدة:

```bash
WORK="$HOME/AlphaX-Railway-$(date +%s)"
git clone https://github.com/plmoknijb7474/AlphaX.git "$WORK"
cd "$WORK"
git remote -v
git branch --show-current
```

تأكد أن `origin` هو `plmoknijb7474/AlphaX` وأن الفرع `main`.

## 3) فك الحزمة فوق نسخة المستودع

```bash
ZIP="$HOME/storage/downloads/AlphaX-Railway-Ready.zip"
ls -lh "$ZIP"
unzip -t "$ZIP"
unzip -o "$ZIP" -d "$WORK"
cd "$WORK"
rm -f render.yaml render_sandbox_probe.py DEPLOY-RENDER-SUPABASE-AR.md tests/test_render_sandbox_adapter.py tests/test_render_sandbox_probe.py
```

فك الضغط يضيف/يحدّث ملفات الحزمة ولا يحذف الملفات التي لا توجد داخل ZIP. لذلك احذف فقط ملفات إعداد Render القديمة المعروفة إن كانت موجودة، واترك `README.md` وأي ملفات أخرى كما هي.

## 4) فحص سريع

```bash
python -m py_compile app.py runtime_sandbox.py railway_runner.py
python -m unittest discover -s tests -p 'test_*.py' -v

git status --short
git diff --check
```

## 5) تجهيز Commit ورفعه بأمان

في مجلد clone الجديد فقط، أضف التغييرات بما فيها إزالة ملفات Render القديمة المحددة أعلاه:

```bash
git add -A
git diff --cached --check
git diff --cached --stat
git commit -m "Move AlphaX runtime to Railway runner"
```

أنشئ Fine-grained Personal Access Token من حساب `plmoknijb7474` للمستودع `AlphaX`، بصلاحية Repository Contents: Read and write. بعد إنشائه شغّل هذا المقطع؛ سيطلب الرمز دون عرضه على الشاشة أو وضعه داخل رابط Git:

```bash
read -r -s -p "GitHub token for plmoknijb7474: " GH_TOKEN
echo
[ -n "$GH_TOKEN" ] || { echo "لم يتم إدخال الرمز"; exit 1; }
export GH_TOKEN
ASKPASS="$(mktemp)"
cat > "$ASKPASS" <<'ASKPASS_EOF'
#!/data/data/com.termux/files/usr/bin/sh
case "$1" in
  *Username*|*username*) printf '%s\n' 'plmoknijb7474' ;;
  *Password*|*password*) printf '%s\n' "$GH_TOKEN" ;;
  *) exit 1 ;;
esac
ASKPASS_EOF
chmod 700 "$ASKPASS"
GIT_ASKPASS="$ASKPASS" GIT_TERMINAL_PROMPT=0 git -c credential.helper= push origin main
PUSH_STATUS=$?
rm -f "$ASKPASS"
unset GH_TOKEN
[ "$PUSH_STATUS" -eq 0 ] || exit "$PUSH_STATUS"
echo "تم رفع AlphaX إلى GitHub بنجاح"
```

لا تستخدم كلمة مرور حساب GitHub بدلاً من الرمز. لا ترسل الرمز في المحادثة ولا تحفظه في GitHub أو ملفات المشروع. إذا فشل إنشاء Commit بسبب هوية Git، اضبط `git config user.name` و`git config user.email` محلياً ثم أعد Commit.

## 6) إعداد Railway

اتبع `DEPLOY-RAILWAY-SUPABASE-AR.md` لإنشاء خدمتي `alpha` و`alpha-runner` وربط المتغيرات الخاصة. لا تنشئ Public Domain لخدمة Runner.
