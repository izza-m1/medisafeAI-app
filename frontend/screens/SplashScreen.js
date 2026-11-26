// brand screen while the app starts, then: signed in → Home, guest → Home (or their details first), nobody → Welcome
import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, StatusBar, Animated, Easing } from 'react-native';
import { onAuthStateChanged, signOut } from 'firebase/auth';
import { Logo, C } from '../ui';
import { auth } from '../firebase';
import { cachedProfile } from '../api';
import { mustVerify } from './SignInScreen';

export default function SplashScreen({ navigation }) {
  const show = useRef(new Animated.Value(0)).current;
  const ring = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(show, { toValue: 1, duration: 700, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
    Animated.loop(Animated.timing(ring, { toValue: 1, duration: 1800, easing: Easing.out(Easing.quad), useNativeDriver: true })).start();
    let user, waited = false, known = false;
    const go = async () => {
      if (!waited || !known) return;
      if (mustVerify(user)) { signOut(auth).catch(() => {}); return navigation.replace('SignIn', { unverified: true }); }
      if (!user) return navigation.replace('Welcome');
      if (user.isAnonymous && !(await cachedProfile())) {
        return navigation.replace('EditProfile', { guest: true, next: 'Home' });
      }
      navigation.replace('Home');
    };
    const stop = onAuthStateChanged(auth, u => { user = u; known = true; go(); });
    const timer = setTimeout(() => { waited = true; go(); }, 1400);
    return () => { clearTimeout(timer); stop(); };
  }, []);

  const scale = show.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] });
  const ringScale = ring.interpolate({ inputRange: [0, 1], outputRange: [1, 1.9] });
  const ringFade = ring.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0] });

  return (
    <View style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor={C.deep} />
      <Animated.View style={{ alignItems: 'center', opacity: show, transform: [{ scale }] }}>
        <View style={s.logoWrap}>
          <Animated.View style={[s.ring, { opacity: ringFade, transform: [{ scale: ringScale }] }]} />
          <Logo size={92} light />
        </View>
        <Text style={s.name}>MediSafe<Text style={{ color: C.mint }}> AI</Text></Text>
        <Text style={s.motto}>Know what you take, before you take it.</Text>
      </Animated.View>

      <Text style={s.foot}>Checked against NIH and USDA data</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root:     { flex: 1, backgroundColor: C.deep, alignItems: 'center', justifyContent: 'center' },
  logoWrap: { width: 120, height: 120, alignItems: 'center', justifyContent: 'center', marginBottom: 22 },
  ring:     { position: 'absolute', width: 92, height: 92, borderRadius: 28, backgroundColor: C.mint },
  name:     { fontSize: 34, fontWeight: '800', color: '#fff', letterSpacing: -0.5 },
  motto:    { fontSize: 15, color: C.onDeep, marginTop: 6 },
  foot:     { position: 'absolute', bottom: 48, fontSize: 13, color: C.onDeep, letterSpacing: 0.3 },
});
