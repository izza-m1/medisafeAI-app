// the Profile tab: who you are, your health details, medicines, other supplements and conditions, with Edit and Sign out.
// Guests see the same details (kept on this phone) and a way to create an account.
import React, { useCallback, useState } from 'react';
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { signOut } from 'firebase/auth';
import { Screen, Button, Icon, Avatar, SectionLabel, ListRow, C, T } from '../ui';
import { LinkText, periodLabel, isoToDob } from '../forms';
import { getProfile, cachedProfile, getMedicines, isGuest, endGuest } from '../api';
import { auth } from '../firebase';

const listOf = items => (items?.length ? items.join(', ') : 'None');

export default function ProfileScreen({ navigation }) {
  const [p, setP] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [medicineNames, setMedicineNames] = useState({});
  useFocusEffect(useCallback(() => {
    cachedProfile().then(c => c && setP(x => x ?? c));                 // the phone's copy shows at once
    getProfile().then(x => { if (x) setP(x); setLoaded(true); });     // then the account's copy
    getMedicines().then(list => setMedicineNames(Object.fromEntries(list.map(m => [m.key, m.name])))).catch(() => {});
  }, []));
  const guest = isGuest();
  const me = auth.currentUser;

  const toWelcome = () => navigation.reset({ index: 0, routes: [{ name: 'Welcome' }] });
  const logout = async () => { await signOut(auth); toWelcome(); };
  const leaveGuest = async () => { await endGuest(); toWelcome(); };
  const female = p?.sex === 'female';
  const yesNo = v => (v ? 'Yes' : 'No');
  const medicines = [...(p?.medicines || []).map(k => medicineNames[k] || k), ...(p?.other_medicines || [])];

  const edit = (
    <Pressable onPress={() => navigation.navigate('EditProfile')} hitSlop={10} style={s.edit}
      accessibilityRole="button" accessibilityLabel="Edit profile">
      <Icon name="create-outline" size={18} color={C.brandDark} />
      <Text style={s.editTxt}>Edit</Text>
    </Pressable>
  );

  return (
    <Screen title="Profile" large bg={C.soft} tabs={{ navigation, current: 'Profile' }} right={p ? edit : null}>
      {!p && !loaded ? <ActivityIndicator color={C.brand} style={{ marginTop: 40 }} /> : <>
        <View style={s.card}>
          <View style={[s.ring, { width: 180, height: 180, top: -80, right: -50 }]} />
          <Avatar name={guest ? '' : p?.name || me?.displayName} sex={p?.sex} size={64} light />
          <View style={{ flex: 1 }}>
            <Text style={s.name} numberOfLines={1}>{guest ? 'Guest' : p?.name || me?.displayName || 'Your profile'}</Text>
            <Text style={s.email} numberOfLines={1}>{guest ? 'Details kept on this phone' : p?.email || me?.email}</Text>
            {p ? (
              <View style={s.tags}>
                {p.age != null ? <Text style={s.tag}>{p.age} years</Text> : null}
                {p.sex ? <Text style={s.tag}>{female ? 'Female' : 'Male'}</Text> : null}
                {p.pregnant ? <Text style={s.tag}>Pregnant</Text> : null}
                {p.breastfeeding ? <Text style={s.tag}>Breastfeeding</Text> : null}
              </View>
            ) : null}
          </View>
        </View>

        {guest ? (
          <View style={s.save}>
            <Text style={T.h3}>Keep your reports</Text>
            <Text style={[T.sub, { marginTop: 2, marginBottom: 12 }]}>Create a free account to save every report and use it on any phone. Your details move with you.</Text>
            <Button label="Create a free account" icon="person-add-outline" onPress={() => navigation.navigate('SignUp')} />
            <Text style={s.have}>Already have one? <LinkText onPress={() => navigation.navigate('SignIn')}>Sign in</LinkText></Text>
          </View>
        ) : null}

        {!p ? (
          <View style={s.save}>
            <Text style={T.h3}>Add your details</Text>
            <Text style={[T.sub, { marginTop: 2, marginBottom: 12 }]}>Your date of birth and gender, once, so every check is made for you.</Text>
            <Button label="Add your details" icon="create-outline" onPress={() => navigation.navigate('EditProfile')} />
          </View>
        ) : <>
          <SectionLabel>About you</SectionLabel>
          <View style={s.list}>
            <ListRow icon="calendar-outline" label="Date of birth" value={p.dob ? isoToDob(p.dob) : 'Not set'} />
            <ListRow icon="person-outline" label="Gender" value={female ? 'Female' : 'Male'} last={!female} />
            {female ? <>
              <ListRow icon="water-outline" label="Periods" value={p.periods ? periodLabel(p.periods) : 'Not asked'} />
              <ListRow icon="heart-outline" label="Pregnant" value={yesNo(p.pregnant)} />
              <ListRow icon="happy-outline" label="Breastfeeding" value={yesNo(p.breastfeeding)} last />
            </> : null}
          </View>

          <SectionLabel>Your health</SectionLabel>
          <View style={s.list}>
            <ListRow icon="medkit-outline" label="Medicines" value={listOf(medicines)} />
            <ListRow icon="nutrition-outline" label="Other supplements" value={listOf(p.other_supplements)} />
            <ListRow icon="fitness-outline" label="Conditions" value={listOf(p.conditions)} last />
          </View>
        </>}

        <View style={s.privacy}>
          <Icon name="lock-closed-outline" size={14} color={C.sub} />
          <Text style={[T.small, { flex: 1 }]}>The AI never sees your name or email, only the health details above.</Text>
        </View>

        {guest
          ? <Button label="Leave guest mode" icon="log-out-outline" kind="danger" onPress={leaveGuest} style={{ marginTop: 18 }} />
          : <Button label="Sign out" icon="log-out-outline" kind="danger" onPress={logout} style={{ marginTop: 18 }} />}
        {guest ? <Text style={[T.small, { textAlign: 'center', marginTop: 8 }]}>This removes the details saved on this phone.</Text> : null}
      </>}
    </Screen>
  );
}

const s = StyleSheet.create({
  card:    { flexDirection: 'row', alignItems: 'center', gap: 16, backgroundColor: C.deep, borderRadius: 24, padding: 20, overflow: 'hidden' },
  ring:    { position: 'absolute', borderRadius: 999, borderWidth: 1, borderColor: 'rgba(142,221,209,0.18)' },
  name:    { fontSize: 20, fontWeight: '800', color: '#fff' },
  email:   { fontSize: 14, color: C.onDeep, marginTop: 2 },
  tags:    { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  tag:     { fontSize: 12, fontWeight: '700', color: C.deep, backgroundColor: C.mint, borderRadius: 8, paddingHorizontal: 8,
             paddingVertical: 3, overflow: 'hidden' },
  save:    { backgroundColor: '#fff', borderRadius: 18, borderWidth: 1, borderColor: C.line, padding: 18, marginTop: 14 },
  have:    { textAlign: 'center', fontSize: 14, color: C.sub, marginTop: 12 },
  list:    { backgroundColor: '#fff', borderRadius: 18, borderWidth: 1, borderColor: C.line, paddingHorizontal: 14 },
  edit:    { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.tint, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8 },
  editTxt: { color: C.brandDark, fontSize: 15, fontWeight: '700' },
  privacy: { flexDirection: 'row', gap: 8, alignItems: 'center', marginTop: 18, paddingHorizontal: 4 },
});
