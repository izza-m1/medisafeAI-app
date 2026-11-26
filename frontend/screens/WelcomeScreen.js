// First screen for someone who isn't signed in: try the app straight away as a guest, or create an account / sign in.
import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated, Easing, StatusBar } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Icon, Logo, Notice, C, T } from '../ui';
import { LinkText } from '../forms';
import { startGuest } from '../api';
import { authMessage, firebaseReady } from '../firebase';

const POINTS = [
  ['scan-outline', 'Scan the pack', 'Or type the name. Local and international brands.'],
  ['shield-checkmark-outline', 'Checked for you', 'Your age, pregnancy, medicines and the NIH limits.'],
  ['chatbubbles-outline', 'Ask anything', 'Answers come only from NIH fact sheets, with sources.'],
];

export default function WelcomeScreen({ navigation }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const show = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(show, { toValue: 1, duration: 600, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
  }, []);
  const rise = show.interpolate({ inputRange: [0, 1], outputRange: [24, 0] });

  const tryIt = async () => {
    setError(null);
    setBusy(true);
    try {
      await startGuest();
      navigation.reset({ index: 0, routes: [{ name: 'EditProfile', params: { guest: true, next: 'Home' } }] });
    } catch (e) {
      setError(authMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor={C.deep} />
      <View style={[s.ring, { width: 420, height: 420, top: -170, right: -170 }]} />
      <View style={[s.ring, { width: 260, height: 260, top: 120, left: -150 }]} />
      <SafeAreaView edges={['top']} style={{ flex: 1 }}>
        <Animated.View style={[s.top, { opacity: show, transform: [{ translateY: rise }] }]}>
          <View style={s.brandRow}>
            <Logo size={40} light />
            <Text style={s.brand}>MediSafe <Text style={{ color: C.mint }}>AI</Text></Text>
          </View>
          <Text style={s.headline}>Know if a supplement is right for you.</Text>
          <View style={{ gap: 16, marginTop: 26 }}>
            {POINTS.map(([icon, title, text]) => (
              <View key={title} style={s.point}>
                <View style={s.pointIcon}><Icon name={icon} size={20} color={C.mint} /></View>
                <View style={{ flex: 1 }}>
                  <Text style={s.pointTitle}>{title}</Text>
                  <Text style={s.pointTxt}>{text}</Text>
                </View>
              </View>
            ))}
          </View>
        </Animated.View>
      </SafeAreaView>

      <SafeAreaView edges={['bottom']} style={s.sheet}>
        {error ? <Notice kind="stop">{error}</Notice> : null}
        <Button label="Try it now" icon="arrow-forward" onPress={tryIt} loading={busy} disabled={!firebaseReady} />
        <Text style={s.note}>No account needed. Your details stay on this phone.</Text>
        <Button label="Create a free account" kind="secondary" onPress={() => navigation.navigate('SignUp')} />
        <Text style={s.switch}>Already have an account? <LinkText onPress={() => navigation.navigate('SignIn')}>Sign in</LinkText></Text>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  root:       { flex: 1, backgroundColor: C.deep, overflow: 'hidden' },
  ring:       { position: 'absolute', borderRadius: 999, borderWidth: 1, borderColor: 'rgba(142,221,209,0.16)' },
  top:        { flex: 1, paddingHorizontal: 24, paddingTop: 28 },
  brandRow:   { flexDirection: 'row', alignItems: 'center', gap: 10 },
  brand:      { fontSize: 20, fontWeight: '800', color: '#fff', letterSpacing: 0.2 },
  headline:   { fontSize: 32, lineHeight: 39, fontWeight: '800', color: '#fff', marginTop: 34, letterSpacing: -0.5 },
  point:      { flexDirection: 'row', gap: 14, alignItems: 'center' },
  pointIcon:  { width: 42, height: 42, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' },
  pointTitle: { fontSize: 16, fontWeight: '700', color: '#fff' },
  pointTxt:   { fontSize: 14, lineHeight: 20, color: C.onDeep, marginTop: 1 },
  sheet:      { backgroundColor: '#fff', borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingHorizontal: 22, paddingTop: 24, gap: 10 },
  note:       { ...T.small, textAlign: 'center', marginBottom: 6 },
  switch:     { textAlign: 'center', fontSize: 15, color: C.sub, marginTop: 6, marginBottom: 10 },
});
