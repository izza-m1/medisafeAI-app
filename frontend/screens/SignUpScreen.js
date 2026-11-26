// Sign up in a few short steps (no long scrolling form):
//   1 Account (name, email) · 2 Password · 3 About you (date of birth, gender) · 4 Women's health (females only)
//   · 5 Medicines, other supplements and conditions (optional, can be skipped)
// A guest who signs up keeps what they already entered: only steps 1 and 2 are asked, and the guest is linked to the
// new account (same user id), so their details move to the account.
import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { Formik } from 'formik';
import * as Yup from 'yup';
import { createUserWithEmailAndPassword, linkWithCredential, EmailAuthProvider, updateProfile, sendEmailVerification, signOut } from 'firebase/auth';
import { Screen, Button, Notice, Icon, IconCircle, C, T } from '../ui';
import { Field, PasswordField, DobField, Choice, LinkText, HealthFields, HEALTH_RULES, PERIOD_OPTIONS, dobToIso, ageFrom, splitList } from '../forms';
import { auth, authMessage } from '../firebase';
import { checkAvailable, saveProfile, cachedProfile, getMedicines, isGuest, errorMessage } from '../api';

const NAME = /^[A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF .'-]{1,39}$/;

const STEPS = [
  { icon: 'person-outline', title: 'Create your account', sub: 'So your reports are saved and you can see them on any phone.', fields: ['name', 'email'] },
  { icon: 'lock-closed-outline', title: 'Choose a password', sub: 'At least 8 characters, with a capital letter and a number.', fields: ['password', 'confirm'] },
  { icon: 'calendar-outline', title: 'A little about you', sub: 'Your age and gender decide which doses are right for you.', fields: ['dob', 'sex'] },
  { icon: 'female-outline', title: "Women's health", sub: 'Periods, pregnancy and breastfeeding change what your body needs.', fields: ['periods', 'pregnant', 'breastfeeding'] },
  { icon: 'medkit-outline', title: 'Your health', sub: 'Optional. Every report checks the supplement against these. You can add them later in Profile.',
    fields: ['otherMedicines', 'otherSupplements', 'conditions'], optional: true },
];

// The shape of an email is checked here; the server also checks for typos (gmial.com) and fake endings (.con).
const EMAIL = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;
const BAD_EMAIL = "That email doesn't look right. Use a full address like name@gmail.com.";

const age = v => ageFrom(dobToIso(v));
const asksPregnancy = v => v.sex === 'female' && age(v.dob) >= 12 && age(v.dob) <= 55 && !(age(v.dob) >= 35 && v.periods === 'no');

const schema = Yup.object({
  name: Yup.string().trim().required('Enter your name.').matches(NAME, 'Letters and spaces only, 2-40 characters.'),
  email: Yup.string().trim().required('Enter your email.').matches(EMAIL, BAD_EMAIL),
  password: Yup.string().required('Choose a password.').min(8, 'At least 8 characters.')
    .matches(/[A-Z]/, 'Use at least one capital letter.').matches(/\d/, 'Use at least one number.'),
  confirm: Yup.string().required('Type your password again.').oneOf([Yup.ref('password')], "The passwords don't match."),
  dob: Yup.string().required('Enter your date of birth.')
    .test('real', 'Enter a real date as DD/MM/YYYY.', v => !!dobToIso(v))
    .test('range', 'Age must be between 1 and 120.', v => !dobToIso(v) || (age(v) >= 1 && age(v) <= 120)),
  sex: Yup.string().required('Choose one.'),
  periods: Yup.string().nullable().when(['sex', 'dob'], ([sex, dob], sc) =>
    sex === 'female' && age(dob) >= 8 ? sc.required('Choose one.') : sc),
  pregnant: Yup.boolean().nullable().test('asked', 'Choose one.', function (v) { return !asksPregnancy(this.parent) || v !== null; }),
  breastfeeding: Yup.boolean().nullable().test('asked', 'Choose one.', function (v) { return !asksPregnancy(this.parent) || v !== null; }),
  ...HEALTH_RULES,
});
// a guest already gave their details: only the account and password are checked
const guestSchema = schema.pick(['name', 'email', 'password', 'confirm']);

export default function SignUpScreen({ navigation }) {
  const [step, setStep] = useState(0);
  const [show, setShow] = useState(false);
  const [emailState, setEmailState] = useState(null);  // null | 'checking' | 'free' | 'taken' | the server's reason it's wrong
  const checked = useRef({});                           // email -> the state the server gave it
  const timer = useRef(null);
  const [error, setError] = useState(null);
  const fade = useRef(new Animated.Value(1)).current;
  const [guest] = useState(isGuest);
  const [medicines, setMedicines] = useState([]);
  useEffect(() => { getMedicines().then(setMedicines).catch(() => setMedicines([])); }, []);

  useEffect(() => {
    fade.setValue(0);
    Animated.timing(fade, { toValue: 1, duration: 220, useNativeDriver: true }).start();
  }, [step]);

  // the steps this person sees, in order
  const order = values => guest ? [0, 1] : [0, 1, 2, ...(values.sex === 'female' && age(values.dob) >= 8 ? [3] : []), 4];

  // Checks the email while the user types (after a short pause). Returns true when it can't be used.
  const checkEmail = async (raw) => {
    const email = raw.trim().toLowerCase();
    if (!EMAIL.test(email)) return false;
    if (!(email in checked.current)) {
      setEmailState('checking');
      const r = await checkAvailable(email);
      if (r.email_taken === null && !r.problem) { setEmailState(null); return false; }  // couldn't check: Firebase catches it at the end
      checked.current[email] = r.problem || (r.email_taken ? 'taken' : 'free');
    }
    setEmailState(checked.current[email]);
    return checked.current[email] !== 'free';
  };
  const onEmail = (t, setFieldValue) => {
    setFieldValue('email', t);
    setEmailState(null);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => checkEmail(t), 600);
  };

  const next = async (form) => {
    const { values, validateForm, setTouched } = form;
    const fields = STEPS[step].fields;
    const errs = await validateForm();
    setTouched(Object.fromEntries(fields.map(k => [k, true])), false);
    if (fields.some(k => errs[k])) return;
    if (step === 0) {                                     // email already used? (usually already checked while typing)
      const taken = await checkEmail(values.email);
      if (taken) return;                                  // message is shown under the email box
    }
    const steps = order(values);
    const at = steps.indexOf(step);
    if (at < steps.length - 1) setStep(steps[at + 1]);
    else form.submitForm();
  };
  const back = values => {
    const steps = order(values);
    const at = steps.indexOf(step);
    at > 0 ? setStep(steps[at - 1]) : navigation.goBack();
  };

  const create = async (v, { setSubmitting }) => {
    setError(null);
    try {
      const female = v.sex === 'female';
      const health = { medicines: v.medicines, other_medicines: splitList(v.otherMedicines),
                       other_supplements: splitList(v.otherSupplements), conditions: splitList(v.conditions) };
      const profile = guest ? { ...(await cachedProfile()), name: v.name.trim() } : {
        name: v.name.trim(), dob: dobToIso(v.dob), sex: v.sex,
        periods: female && age(v.dob) >= 8 ? v.periods : null,
        pregnant: asksPregnancy(v) ? !!v.pregnant : false, breastfeeding: asksPregnancy(v) ? !!v.breastfeeding : false,
        ...health,
      };
      delete profile.age;
      delete profile._pending;
      const email = v.email.trim();
      const cred = await withTimeout(guest
        ? linkWithCredential(auth.currentUser, EmailAuthProvider.credential(email, v.password))   // the guest becomes this account
        : createUserWithEmailAndPassword(auth, email, v.password), 20000);
      updateProfile(cred.user, { displayName: profile.name }).catch(() => {});
      await saveProfile(profile, { offlineOk: true });    // if the server is slow, it is kept on the phone and sent later
      // Email check: Firebase sends a link to the address; only the real owner can open it.
      // The app stays locked until it is confirmed: sign out and ask them to sign in after opening the link.
      await sendEmailVerification(cred.user).catch(() => {});
      await signOut(auth);
      navigation.reset({ index: 0, routes: [{ name: 'SignIn', params: { verify: v.email.trim() } }] });
    } catch (e) {
      if (['auth/email-already-in-use', 'auth/credential-already-in-use'].includes(e.code)) { setStep(0); setEmailState('taken'); return; }
      setError(e.message === 'timeout' ? 'No internet connection. Check your connection and try again.'
        : e.response ? errorMessage(e) : authMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Formik validationSchema={guest ? guestSchema : schema} onSubmit={create} validateOnChange={false}
      initialValues={{ name: '', email: '', password: '', confirm: '', dob: '', sex: null,
                       periods: null, pregnant: null, breastfeeding: null,
                       medicines: [], otherMedicines: '', otherSupplements: '', conditions: '' }}>
      {form => {
        const { values, errors, touched, handleChange, handleBlur, setFieldValue, isSubmitting } = form;
        const err = k => touched[k] && errors[k];
        const steps = order(values);
        const at = steps.indexOf(step);
        const done = at === steps.length - 1;
        const info = STEPS[step];
        return (
          <Screen onBack={() => back(values)} scroll
            footer={<>
              <Button label={done ? 'Create account' : 'Continue'} icon={done ? 'checkmark' : 'arrow-forward'}
                onPress={() => next(form)} loading={isSubmitting} />
              {info.optional ? <Button label="Skip for now" kind="ghost" small onPress={() => form.submitForm()} disabled={isSubmitting} /> : (
                <Text style={s.switch}>Already have an account? <LinkText onPress={() => navigation.navigate('SignIn')}>Sign in</LinkText></Text>
              )}
            </>}>
            <View style={s.body}>
              <View style={s.progress} accessibilityLabel={`Step ${at + 1} of ${steps.length}`}>
                {steps.map((k, i) => <View key={k} style={[s.bar, i <= at && s.barOn]} />)}
              </View>
              <Text style={s.stepNo}>Step {at + 1} of {steps.length}</Text>
              <Animated.View style={{ opacity: fade, gap: 16 }}>
                <View style={{ gap: 12 }}>
                  <IconCircle name={info.icon} size={52} color={C.brandDark} />
                  <View>
                    <Text style={T.title}>{info.title}</Text>
                    <Text style={[T.sub, { marginTop: 4 }]}>{info.sub}</Text>
                  </View>
                  {guest && step === 0 ? <Notice kind="info" icon="sparkles-outline">Your health details from guest mode move to the new account.</Notice> : null}
                </View>

                {step === 0 && <>
                  <Field label="Full name" icon="person-outline" value={values.name} onChangeText={handleChange('name')}
                    onBlur={handleBlur('name')} placeholder="e.g. Izza Maryam" autoCapitalize="words" error={err('name')} />
                  <Field label="Email" icon="mail-outline" value={values.email} placeholder="you@example.com"
                    onChangeText={t => onEmail(t, setFieldValue)}
                    onBlur={e => { handleBlur('email')(e); checkEmail(values.email); }} keyboardType="email-address"
                    autoCapitalize="none" autoCorrect={false}
                    error={err('email') || (emailState === 'taken' ? 'This email already has an account.'
                      : !['checking', 'free', null].includes(emailState) ? emailState : null)}
                    hint={emailState === 'checking' ? 'Checking…' : emailState === 'free' ? 'Email is free to use' : null} />
                  {emailState === 'taken' ? (
                    <Text style={s.hint}>Is it yours? <LinkText onPress={() => navigation.navigate('SignIn')}>Sign in instead</LinkText></Text>
                  ) : null}
                </>}

                {step === 1 && <>
                  <PasswordField label="Password" value={values.password} onChangeText={handleChange('password')}
                    onBlur={handleBlur('password')} placeholder="8+ characters, a capital letter and a number"
                    textContentType="newPassword" show={show} onToggle={() => setShow(v => !v)} error={err('password')} />
                  <PasswordField label="Confirm password" value={values.confirm} onChangeText={handleChange('confirm')}
                    onBlur={handleBlur('confirm')} placeholder="Type it again" show={show} onToggle={() => setShow(v => !v)}
                    error={err('confirm')} />
                  <Strength password={values.password} />
                </>}

                {step === 2 && <>
                  <DobField value={values.dob} onChange={v => setFieldValue('dob', v)} error={err('dob')} />
                  <Choice label="Gender" value={values.sex} error={err('sex')}
                    onChange={v => { setFieldValue('sex', v); if (v === 'male') { setFieldValue('periods', null); setFieldValue('pregnant', null); setFieldValue('breastfeeding', null); } }}
                    options={[{ value: 'male', label: 'Male' }, { value: 'female', label: 'Female' }]} />
                </>}

                {step === 3 && <>
                  <Choice label="Periods" value={values.periods} onChange={v => setFieldValue('periods', v)}
                    error={err('periods')} options={PERIOD_OPTIONS} />
                  {asksPregnancy(values) && <>
                    <Choice label="Are you pregnant?" value={values.pregnant} onChange={v => setFieldValue('pregnant', v)}
                      error={err('pregnant')} options={[{ value: false, label: 'No' }, { value: true, label: 'Yes' }]} />
                    <Choice label="Are you breastfeeding?" value={values.breastfeeding} onChange={v => setFieldValue('breastfeeding', v)}
                      error={err('breastfeeding')} options={[{ value: false, label: 'No' }, { value: true, label: 'Yes' }]} />
                  </>}
                </>}

                {step === 4 && <HealthFields form={form} medicines={medicines} err={err} />}

                {error ? <Notice kind="stop">{error}</Notice> : null}
              </Animated.View>
            </View>
          </Screen>
        );
      }}
    </Formik>
  );
}

// Gives up after `ms` (so a bad connection shows a message instead of loading forever)
const withTimeout = (p, ms) => Promise.race([p, new Promise((_, no) => setTimeout(() => no(new Error('timeout')), ms))]);

// Live password checklist
function Strength({ password }) {
  const rules = [['8+ characters', password.length >= 8], ['A capital letter', /[A-Z]/.test(password)], ['A number', /\d/.test(password)]];
  return (
    <View style={s.rules}>
      {rules.map(([label, ok]) => (
        <View key={label} style={s.rule}>
          <Icon name={ok ? 'checkmark-circle' : 'ellipse-outline'} size={16} color={ok ? C.safe : C.faint} />
          <Text style={[T.small, ok && { color: C.safe }]}>{label}</Text>
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  body:     { paddingTop: 4 },
  progress: { flexDirection: 'row', gap: 6 },
  bar:      { flex: 1, height: 4, borderRadius: 2, backgroundColor: C.line },
  barOn:    { backgroundColor: C.brand },
  stepNo:   { fontSize: 13, fontWeight: '600', color: C.sub, marginTop: 8, marginBottom: 18 },
  switch:   { textAlign: 'center', fontSize: 15, color: C.sub, marginTop: 4 },
  rules:    { flexDirection: 'row', gap: 16, flexWrap: 'wrap' },
  hint:     { fontSize: 14, color: C.sub, marginTop: -6 },
  rule:     { flexDirection: 'row', alignItems: 'center', gap: 5 },
});
