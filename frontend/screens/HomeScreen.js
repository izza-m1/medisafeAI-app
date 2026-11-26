// greeting, the main card (scan or search), a guest reminder, nutrient cards that slide by themselves (tap one to read
// more), how it works, and one plain line at the bottom: for information only. History and Profile have their own tabs.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, Pressable, ScrollView, Modal, Animated, PanResponder, StyleSheet, useWindowDimensions, Linking } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { Screen, Icon, Logo, Avatar, SectionLabel, C, T } from '../ui';
import { getProfile, cachedProfile, isGuest } from '../api';
import NUTRIENT_CARDS from '../data/nutrients.json';

// Nutrient cards from data/nutrients.json. A different 6 are shown each time Home opens.
const NUTRIENTS = NUTRIENT_CARDS.nutrients;
const shuffled = () => [...NUTRIENTS].sort(() => Math.random() - 0.5).slice(0, 6);
const EVERY = 5000;        // ms each card stays before the next one slides in
const RESUME = 6000;       // after the user swipes, wait this long before sliding again

// The card, opened: a sheet from the bottom. Drag the handle (or the title) down to close it, or tap outside it.
function NutrientSheet({ item, onClose }) {
  const { height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const y = useRef(new Animated.Value(0)).current;
  useEffect(() => { if (item) y.setValue(0); }, [item]);

  const pan = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: (_, g) => g.dy > 4,
    onPanResponderMove: (_, g) => y.setValue(Math.max(0, g.dy)),
    onPanResponderRelease: (_, g) => {
      if (g.dy > 90 || g.vy > 0.8) {
        Animated.timing(y, { toValue: height, duration: 180, useNativeDriver: true }).start(onClose);
      } else {
        Animated.spring(y, { toValue: 0, useNativeDriver: true, bounciness: 4 }).start();
      }
    },
  })).current;

  return (
    <Modal visible={!!item} transparent animationType="slide" statusBarTranslucent onRequestClose={onClose}>
      <Pressable style={s.dim} onPress={onClose} accessibilityLabel="Close" />
      {item && (
        <Animated.View style={[s.sheet, { maxHeight: height * 0.85, paddingBottom: insets.bottom + 16, transform: [{ translateY: y }] }]}>
          <View {...pan.panHandlers}>
            <View style={s.grabArea}><View style={s.grab} /></View>
            <View style={s.sheetHead}>
              <View style={s.factIcon}><Icon name={item.icon} size={24} color={C.brand} /></View>
              <View style={{ flex: 1 }}>
                <Text style={s.sheetTitle}>{item.name}</Text>
                <Text style={s.factTxt}>{item.tag}</Text>
              </View>
            </View>
          </View>
          <ScrollView style={{ flexShrink: 1 }} contentContainerStyle={{ paddingBottom: 8 }}>
            <Text style={s.h}>What it does</Text>
            <Text style={s.p}>{item.does}</Text>
            <Text style={s.h}>Good to know</Text>
            <Text style={s.p}>{item.good}</Text>
            <Text style={s.h}>Fruits and vegetables</Text>
            <View style={s.chips}>
              {item.fruitsVeg.map(x => <View key={x} style={s.chip}><Text style={s.chipTxt}>{x}</Text></View>)}
            </View>
            <Text style={s.h}>Other natural sources</Text>
            <Text style={s.p}>{item.other}</Text>
            <Text style={s.h}>Adults need</Text>
            <Text style={s.p}>{item.need}</Text>
            <View style={s.foodBox}>
              <View style={s.foodHead}>
                <Icon name="restaurant-outline" size={18} color={C.brandDark} />
                <Text style={s.foodLabel}>Food fact</Text>
              </View>
              <Text style={s.foodTxt}>{item.food}</Text>
            </View>
            <Text style={s.src} onPress={() => Linking.openURL(item.source)} accessibilityRole="link">
              Source: NIH Office of Dietary Supplements fact sheet
            </Text>
          </ScrollView>
        </Animated.View>
      )}
    </Modal>
  );
}

function Facts() {
  const [FACTS] = useState(shuffled);                     // a fresh set each time Home opens
  const { width } = useWindowDimensions();
  const cardW = width - 40;                               // same side margins as the rest of the page
  const step = cardW + 12;
  const ref = useRef(null);
  const [index, setIndex] = useState(0);
  const at = useRef(0);                                   // the card on screen now
  const [paused, setPaused] = useState(false);            // user swiping, or a card is open
  const [open, setOpen] = useState(null);                 // the nutrient whose details are showing
  const resumeTimer = useRef(null);

  useEffect(() => {
    if (paused || open) return;
    const t = setInterval(() => {
      const next = (at.current + 1) % FACTS.length;
      at.current = next;
      setIndex(next);
      ref.current?.scrollTo({ x: next * step, animated: true });
    }, EVERY);
    return () => clearInterval(t);
  }, [paused, open, step]);
  useEffect(() => () => clearTimeout(resumeTimer.current), []);

  const hold = () => { clearTimeout(resumeTimer.current); setPaused(true); };
  const release = e => {
    const i = Math.round(e.nativeEvent.contentOffset.x / step);
    at.current = Math.max(0, Math.min(FACTS.length - 1, i));
    setIndex(at.current);
    clearTimeout(resumeTimer.current);
    resumeTimer.current = setTimeout(() => setPaused(false), RESUME);
  };

  return (
    <View style={{ marginTop: 22, marginBottom: 22 }}>
      <Text style={s.section}>Know your nutrients</Text>
      <ScrollView ref={ref} horizontal showsHorizontalScrollIndicator={false} decelerationRate="fast"
        snapToInterval={step} snapToAlignment="start" disableIntervalMomentum
        style={{ marginHorizontal: -20 }} contentContainerStyle={{ paddingHorizontal: 20, gap: 12 }}
        onScrollBeginDrag={hold} onMomentumScrollEnd={release} onScrollEndDrag={release}>
        {FACTS.map(f => (
          <Pressable key={f.key} onPress={() => setOpen(f)} style={({ pressed }) => [s.fact, { width: cardW }, pressed && { opacity: 0.9 }]}
            accessibilityRole="button" accessibilityLabel={`${f.name}. ${f.tag}. Tap to read more`}>
            <View style={s.factIcon}><Icon name={f.icon} size={24} color={C.brand} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.factTitle}>{f.name}</Text>
              <Text style={s.factTxt}>{f.tag}</Text>
              <Text style={s.factMore}>Tap to read more</Text>
            </View>
          </Pressable>
        ))}
      </ScrollView>
      <View style={s.dots}>
        {FACTS.map((f, i) => <View key={f.key} style={[s.dot, i === index && s.dotOn]} />)}
      </View>

      <NutrientSheet item={open} onClose={() => setOpen(null)} />
    </View>
  );
}

export default function HomeScreen({ navigation }) {
  const [profile, setProfile] = useState(null);

  useFocusEffect(useCallback(() => {
    cachedProfile().then(c => c && setProfile(c));     // show at once from the phone
    getProfile().then(p => p && setProfile(p));
  }, []));

  // Search and Scan go straight on: the details saved in the Profile tab are used for every check.
  const go = to => navigation.navigate(to);
  const guest = isGuest();
  const first = profile?.name ? profile.name.split(' ')[0] : null;
  const hour = new Date().getHours();
  const hello = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  const header = (
    <View style={s.header}>
      <Logo size={36} />
      <View style={{ flex: 1 }}>
        <Text style={T.small}>{hello}</Text>
        <Text style={s.name} numberOfLines={1}>{first || (guest ? 'Guest' : 'Welcome')}</Text>
      </View>
      <Pressable onPress={() => navigation.reset({ index: 0, routes: [{ name: 'Profile' }] })} accessibilityRole="button"
        accessibilityLabel="Your profile" hitSlop={8}>
        <Avatar name={profile?.name} sex={profile?.sex} size={40} />
      </Pressable>
    </View>
  );

  return (
    <Screen header={header} bg={C.soft} tabs={{ navigation, current: 'Home' }} footer={
      <View style={s.note}>
        <Icon name="information-circle-outline" size={15} color={C.sub} />
        <Text style={s.noteTxt}>Information only. Follow your doctor's advice.</Text>
      </View>}>
      <View style={s.hero}>
        <View style={[s.ring, { width: 220, height: 220, top: -90, right: -70 }]} />
        <View style={[s.ring, { width: 120, height: 120, bottom: -50, right: 60 }]} />
        <Text style={s.heroTitle}>Is your supplement safe for you?</Text>
        <Text style={s.heroSub}>Scan the pack or type its name. We check it for your age, health and medicines.</Text>
        <Pressable onPress={() => go('Scan')} style={({ pressed }) => [s.scan, pressed && { opacity: 0.9 }]}
          accessibilityRole="button" accessibilityLabel="Scan a supplement">
          <Icon name="scan" size={22} color={C.deep} />
          <Text style={s.scanTxt}>Scan a supplement</Text>
        </Pressable>
        <Pressable onPress={() => go('Search')} style={({ pressed }) => [s.search, pressed && { opacity: 0.85 }]}
          accessibilityRole="search" accessibilityLabel="Search supplements by name">
          <Icon name="search" size={18} color={C.onDeep} />
          <Text style={s.searchTxt}>Search by name</Text>
        </Pressable>
      </View>

      {guest ? (
        <Pressable onPress={() => navigation.navigate('SignUp')} style={({ pressed }) => [s.guest, pressed && { opacity: 0.9 }]}
          accessibilityRole="button">
          <View style={s.guestIcon}><Icon name="cloud-upload-outline" size={20} color={C.brandDark} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.guestTitle}>You're using MediSafe as a guest</Text>
            <Text style={T.small}>Create a free account to save your reports.</Text>
          </View>
          <Icon name="chevron-forward" size={18} color={C.brandDark} />
        </Pressable>
      ) : null}

      <Facts />

      <SectionLabel style={{ marginTop: 0 }}>How it works</SectionLabel>
      <View style={s.how}>
        {[['camera-outline', 'Take a photo', 'of the pack'], ['shield-checkmark-outline', 'We check it', 'for you'],
          ['document-text-outline', 'Read your report', 'dose, foods, safety']].map(([icon, label, sub], i) => (
          <View key={label} style={s.howStep}>
            <View style={s.howIcon}><Icon name={icon} size={20} color={C.brandDark} /><Text style={s.howNo}>{i + 1}</Text></View>
            <Text style={s.howTxt}>{label}</Text>
            <Text style={s.howSub}>{sub}</Text>
          </View>
        ))}
      </View>

    </Screen>
  );
}

const s = StyleSheet.create({
  header:     { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingTop: 10, paddingBottom: 14 },
  name:       { fontSize: 19, fontWeight: '800', color: C.ink },
  hero:       { backgroundColor: C.deep, borderRadius: 26, padding: 22, overflow: 'hidden' },
  ring:       { position: 'absolute', borderRadius: 999, borderWidth: 1, borderColor: 'rgba(142,221,209,0.18)' },
  heroTitle:  { fontSize: 26, lineHeight: 32, fontWeight: '800', color: '#fff', letterSpacing: -0.3, maxWidth: 280 },
  heroSub:    { fontSize: 14, lineHeight: 20, color: C.onDeep, marginTop: 8, marginBottom: 18 },
  scan:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: C.mint,
                borderRadius: 16, minHeight: 54 },
  scanTxt:    { fontSize: 16, fontWeight: '800', color: C.deep },
  search:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 10, borderRadius: 16,
                minHeight: 48, backgroundColor: 'rgba(255,255,255,0.08)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.14)' },
  searchTxt:  { fontSize: 15, fontWeight: '700', color: '#fff' },
  guest:      { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#fff', borderRadius: 18, padding: 14,
                marginTop: 14, borderWidth: 1, borderColor: C.line },
  guestIcon:  { width: 40, height: 40, borderRadius: 12, backgroundColor: C.tint, alignItems: 'center', justifyContent: 'center' },
  guestTitle: { fontSize: 15, fontWeight: '700', color: C.ink },
  fact:       { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: '#fff', borderRadius: 18, padding: 16,
                minHeight: 104, borderWidth: 1, borderColor: C.line },
  factIcon:   { width: 48, height: 48, borderRadius: 24, backgroundColor: C.tint, alignItems: 'center', justifyContent: 'center' },
  factTitle:  { fontSize: 16, fontWeight: '700', color: C.ink },
  factTxt:    { fontSize: 14, lineHeight: 20, color: C.sub, marginTop: 3 },
  dots:       { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 10 },
  dot:        { width: 6, height: 6, borderRadius: 3, backgroundColor: C.line },
  dotOn:      { width: 18, backgroundColor: C.brand },
  factMore:   { fontSize: 13, fontWeight: '600', color: C.brandDark, marginTop: 6 },
  dim:        { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet:      { position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: '#fff', borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingHorizontal: 20 },
  grabArea:   { paddingTop: 10, paddingBottom: 14, alignItems: 'center' },
  grab:       { width: 44, height: 5, borderRadius: 3, backgroundColor: C.line },
  sheetHead:  { flexDirection: 'row', alignItems: 'center', gap: 14, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: C.line },
  sheetTitle: { fontSize: 20, fontWeight: '800', color: C.ink },
  h:          { fontSize: 13, fontWeight: '700', color: C.sub, letterSpacing: 0.6, textTransform: 'uppercase', marginTop: 16, marginBottom: 6 },
  p:          { fontSize: 16, lineHeight: 23, color: C.ink },
  chips:      { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip:       { backgroundColor: C.tint, borderRadius: 16, paddingVertical: 6, paddingHorizontal: 12 },
  chipTxt:    { fontSize: 14, fontWeight: '600', color: C.brandDark },
  foodBox:    { backgroundColor: C.tint, borderRadius: 14, padding: 14, marginTop: 18 },
  foodHead:   { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  foodLabel:  { fontSize: 13, fontWeight: '700', color: C.brandDark, letterSpacing: 0.6, textTransform: 'uppercase' },
  foodTxt:    { fontSize: 16, lineHeight: 23, color: C.ink },
  src:        { fontSize: 12, color: C.faint, marginTop: 18 },
  section:    { ...T.label, marginTop: 0, marginBottom: 10, marginLeft: 4 },
  how:        { flexDirection: 'row', gap: 8, backgroundColor: '#fff', borderRadius: 18, borderWidth: 1, borderColor: C.line, padding: 14 },
  howStep:    { flex: 1, alignItems: 'center', gap: 3 },
  howIcon:    { width: 44, height: 44, borderRadius: 14, backgroundColor: C.tint, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  howNo:      { position: 'absolute', top: -6, right: -6, width: 18, height: 18, borderRadius: 9, backgroundColor: C.brand,
                color: '#fff', fontSize: 11, fontWeight: '800', textAlign: 'center', lineHeight: 18, overflow: 'hidden' },
  howTxt:     { fontSize: 13, fontWeight: '700', color: C.ink, textAlign: 'center' },
  howSub:     { fontSize: 12, color: C.sub, textAlign: 'center' },
  note:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 },
  noteTxt:    { fontSize: 12, color: C.sub },
});
