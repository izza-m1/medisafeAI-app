// Sign in with email and password. New users tap "Sign up" below.
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Formik } from 'formik';
import * as Yup from 'yup';
import { signInWithEmailAndPassword, sendPasswordResetEmail, sendEmailVerification, signOut } from 'firebase/auth';
import { Screen, Button, Notice, Logo, Icon, C, T } from '../ui';
import { Field, PasswordField, LinkText } from '../forms';
import { auth, authMessage, firebaseReady } from '../firebase';
import { api, errorMessage } from '../api';

// The app opens only after the email is confirmed with the link Firebase sends.
// Guests (anonymous sign-in) have no email, so they are never asked.
export const mustVerify = user => !!user && !user.isAnonymous && !user.emailVerified;

const schema = Yup.object({
  email: Yup.string().trim().required('Enter your email.').email('Enter a valid email.'),
  password: Yup.string().required('Enter your password.'),
});

export default function SignInScreen({ navigation, route }) {
  const [show, setShow] = useState(false);
  const verifyFor = route?.params?.verify;
  const [msg, setMsg]   = useState(verifyFor ? { kind: 'caution', text: `We sent a link to ${verifyFor}. Open it to confirm your email, then sign in here (check spam too).` }
    : route?.params?.unverified ? { kind: 'caution', text: 'Confirm your email first: open the link we sent you, then sign in.' } : null);          // { kind, text }

  const signIn = async ({ email, password }, { setSubmitting }) => {
    setMsg(null);
    email = email.trim();
    try {
      const cred = await signInWithEmailAndPassword(auth, email, password);
      await cred.user.reload().catch(() => {});                     // picks up a link opened a moment ago
      if (mustVerify(auth.currentUser)) {
        await sendEmailVerification(cred.user).catch(() => {});     // a fresh link, in case the first one was lost
        await signOut(auth);
        setMsg({ kind: 'caution', text: `Confirm your email first. We sent a link to ${email}. Open it, then sign in again (check spam too).` });
        return;
      }
      navigation.replace('Home');
    } catch (e) {
      setMsg({ kind: 'stop', text: e.response ? errorMessage(e) : authMessage(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const forgot = async email => {
    setMsg(null);
    email = email.trim();
    try {
      const check = await api.post('/account-exists', { email }, { timeout: 8000 }).catch(() => null);
      if (check?.data?.exists === false) return setMsg({ kind: 'caution', text: `There is no account with ${email}.` });
      await sendPasswordResetEmail(auth, email);
      setMsg({ kind: 'ok', text: `We sent a reset link to ${email}. Check your spam folder too.` });
    } catch (e) {
      setMsg({ kind: 'stop', text: e.response ? errorMessage(e) : authMessage(e) });
    }
  };

  return (
    <Formik initialValues={{ email: '', password: '' }} validationSchema={schema} onSubmit={signIn}>
      {({ values, errors, touched, handleChange, handleBlur, handleSubmit, isSubmitting }) => (
        <Screen bg={C.deep} dark edges={['top']} contentStyle={{ flexGrow: 1, paddingBottom: 0 }} header={
          <View style={s.hero}>
            <Pressable onPress={() => (navigation.canGoBack() ? navigation.goBack() : navigation.replace('Welcome'))} hitSlop={14}
              style={s.back} accessibilityRole="button" accessibilityLabel="Go back">
              <Icon name="chevron-back" size={22} color="#fff" />
            </Pressable>
            <Logo size={52} light />
            <Text style={s.title}>Welcome back</Text>
            <Text style={s.motto}>Sign in to see your saved reports.</Text>
          </View>}>
          <View style={s.sheet}>
            {!firebaseReady && <Notice kind="caution" title="Firebase is not set up yet">Paste your Firebase web config into frontend/firebase.js.</Notice>}

            <View style={{ gap: 14 }}>
              <Field label="Email" icon="mail-outline" value={values.email}
                onChangeText={handleChange('email')} onBlur={handleBlur('email')}
                placeholder="you@gmail.com" autoCapitalize="none" autoCorrect={false}
                keyboardType="email-address" textContentType="emailAddress"
                error={touched.email && errors.email} />
              <PasswordField label="Password" value={values.password} onChangeText={handleChange('password')}
                onBlur={handleBlur('password')} placeholder="Your password" textContentType="password"
                show={show} onToggle={() => setShow(v => !v)} error={touched.password && errors.password} />
            </View>

            <View style={s.row}>
              <LinkText onPress={() => values.email.includes('@')
                ? forgot(values.email)
                : setMsg({ kind: 'caution', text: 'Type your email first.' })}>Forgot password?</LinkText>
            </View>

            {msg ? <View style={{ marginTop: 14 }}><Notice kind={msg.kind}>{msg.text}</Notice></View> : null}

            <View style={{ marginTop: 22 }}>
              <Button label="Sign in" onPress={handleSubmit} loading={isSubmitting} disabled={!firebaseReady} />
            </View>

            <Text style={s.switch}>
              New to MediSafe? <LinkText onPress={() => navigation.navigate('SignUp')}>Create an account</LinkText>
            </Text>
          </View>
        </Screen>
      )}
    </Formik>
  );
}

const s = StyleSheet.create({
  hero:   { alignItems: 'center', paddingTop: 8, paddingBottom: 34, paddingHorizontal: 20 },
  back:   { alignSelf: 'flex-start', width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.1)',
            alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  title:  { fontSize: 26, fontWeight: '800', color: '#fff', marginTop: 14 },
  motto:  { fontSize: 15, color: C.onDeep, marginTop: 4 },
  sheet:  { flex: 1, backgroundColor: '#fff', borderTopLeftRadius: 28, borderTopRightRadius: 28, marginHorizontal: -20, marginTop: -8,
            padding: 22, paddingTop: 26, paddingBottom: 44 },
  row:    { alignItems: 'flex-end', marginTop: 10 },
  switch: { textAlign: 'center', fontSize: 15, color: C.sub, marginTop: 24 },
});
