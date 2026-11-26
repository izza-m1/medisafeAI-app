// colours, text styles and the building blocks every screen shares
import React, { useState } from 'react';
import { View, Text, Image, Pressable, StyleSheet, StatusBar, ScrollView, ActivityIndicator, Platform, KeyboardAvoidingView } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

// Calm teal theme. Green, orange and red are kept only for safety results, so they never mix with the brand colour.
export const C = {
  bg:        '#FFFFFF',
  soft:      '#F2F6F5',
  ink:       '#0B2523',
  sub:       '#4B6563',
  faint:     '#8FA5A2',
  line:      '#E1EAE8',
  brand:     '#0E7C7B',
  brandDark: '#0A5958',
  deep:      '#073B3A',
  tint:      '#E3F3F1',
  mint:      '#8EDDD1',
  onDeep:    '#B9E3DD',
  safe:      '#1E7D3A', safeBg:    '#E7F4EA',
  caution:   '#B45309', cautionBg: '#FEF1DF',
  danger:    '#C0261A', dangerBg:  '#FCE9E7',
};

export const T = StyleSheet.create({
  hero:  { fontSize: 30, lineHeight: 36, fontWeight: '800', color: C.ink, letterSpacing: -0.4 },
  title: { fontSize: 26, lineHeight: 32, fontWeight: '800', color: C.ink, letterSpacing: -0.3 },
  h2:    { fontSize: 20, lineHeight: 26, fontWeight: '700', color: C.ink },
  h3:    { fontSize: 17, lineHeight: 23, fontWeight: '700', color: C.ink },
  body:  { fontSize: 16, lineHeight: 24, color: C.ink },
  sub:   { fontSize: 15, lineHeight: 22, color: C.sub },
  small: { fontSize: 13, lineHeight: 19, color: C.sub },
  label: { fontSize: 12, lineHeight: 16, fontWeight: '700', color: C.sub, letterSpacing: 0.8, textTransform: 'uppercase' },
});

export const Icon = ({ name, size = 22, color = C.ink, style }) =>
  <Ionicons name={name} size={size} color={color} style={style} />;

export const STATUS = {
  ok:      { icon: 'checkmark-circle', color: C.safe,    bg: C.safeBg },
  caution: { icon: 'alert-circle',     color: C.caution, bg: C.cautionBg },
  stop:    { icon: 'close-circle',     color: C.danger,  bg: C.dangerBg },
  info:    { icon: 'information-circle', color: C.sub,   bg: C.soft },
};

export const shadow = Platform.select({
  ios: { shadowColor: C.deep, shadowOpacity: 0.08, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
  default: { elevation: 2, shadowColor: C.deep },
});

// Screen: header (back, title, step dots), content, footer with the main action.
// large: a big left-aligned title, used on the three tab pages.
export function Screen({ title, subtitle, large, onBack, step, right, children, footer, scroll = true, bg = C.bg, scrollRef, tabs, header, dark, contentStyle, edges }) {
  const Body = scroll ? ScrollView : View;
  const bar = header || (large ? (
    <View style={s.largeBar}>
      <View style={{ flex: 1 }}>
        <Text style={T.title}>{title}</Text>
        {subtitle ? <Text style={[T.small, { marginTop: 2 }]}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  ) : (
    <View style={s.bar}>
      <View style={s.side}>
        {onBack ? (
          <Pressable onPress={onBack} hitSlop={14} style={s.back} accessibilityRole="button" accessibilityLabel="Go back">
            <Icon name="chevron-back" size={22} color={C.ink} />
          </Pressable>
        ) : null}
      </View>
      <View style={{ alignItems: 'center', flex: 1 }}>
        {title ? <Text style={s.barTitle} numberOfLines={1}>{title}</Text> : null}
        {step ? (
          <View style={s.dots} accessibilityLabel={`Step ${step} of 3`}>
            {[1, 2, 3].map(i => <View key={i} style={[s.dot, i <= step && s.dotOn, i === step && { width: 22 }]} />)}
          </View>
        ) : null}
      </View>
      <View style={[s.side, { alignItems: 'flex-end' }]}>{right}</View>
    </View>
  ));
  return (
    <SafeAreaView style={[s.root, { backgroundColor: bg }]} edges={edges || (tabs ? ['top'] : ['top', 'bottom'])}>
      <StatusBar barStyle={dark ? 'light-content' : 'dark-content'} backgroundColor={bg} />
      {bar}
      {/* the keyboard pushes the content up instead of covering what you type */}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding">
        <Body style={{ flex: 1 }} {...(scroll ? { ref: scrollRef, contentContainerStyle: [s.content, contentStyle], keyboardShouldPersistTaps: 'handled',
                                                   automaticallyAdjustKeyboardInsets: true, showsVerticalScrollIndicator: false } : {})}>
          {children}
        </Body>
        {footer ? <View style={[s.footer, { backgroundColor: bg }]}>{footer}</View> : null}
      </KeyboardAvoidingView>
      {tabs ? <TabBar navigation={tabs.navigation} current={tabs.current} /> : null}
    </SafeAreaView>
  );
}

export function Button({ label, icon, onPress, kind = 'primary', disabled, loading, small, style }) {
  const look = {
    primary:   { bg: C.brand, fg: '#fff' },
    secondary: { bg: '#fff', fg: C.brandDark, border: C.line },
    soft:      { bg: C.tint, fg: C.brandDark },
    ghost:     { bg: 'transparent', fg: C.brandDark },
    white:     { bg: '#fff', fg: C.deep },
    danger:    { bg: '#fff', fg: C.danger, border: C.line },
  }[kind];
  return (
    <Pressable onPress={onPress} disabled={disabled || loading} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed }) => [s.btn, small && s.btnSmall, { backgroundColor: look.bg },
        look.border && { borderWidth: 1.5, borderColor: look.border }, pressed && { opacity: 0.85, transform: [{ scale: 0.99 }] },
        (disabled || loading) && { opacity: 0.45 }, style]}>
      {loading ? <ActivityIndicator color={look.fg} /> : (
        <>
          {icon ? <Icon name={icon} size={small ? 18 : 20} color={look.fg} /> : null}
          <Text style={[s.btnTxt, small && { fontSize: 15 }, { color: look.fg }]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

// Bottom navigation for the three main pages, with labels; the open page sits in a soft teal pill.
const TABS = [{ name: 'Home', icon: 'home' }, { name: 'History', icon: 'time' }, { name: 'Profile', icon: 'person' }];
export function TabBar({ navigation, current }) {
  const { bottom } = useSafeAreaInsets();
  return (
    <View style={[s.tabs, { paddingBottom: bottom ? Math.round(bottom * 0.7) + 4 : 10 }]} accessibilityRole="tablist">
      {TABS.map(t => {
        const on = t.name === current;
        return (
          <Pressable key={t.name} style={s.tab} accessibilityRole="tab" accessibilityLabel={t.name} accessibilityState={{ selected: on }}
            onPress={() => !on && navigation.reset({ index: 0, routes: [{ name: t.name }] })}>
            <View style={[s.tabPill, on && { backgroundColor: C.tint }]}>
              <Icon name={on ? t.icon : `${t.icon}-outline`} size={22} color={on ? C.brandDark : C.faint} />
            </View>
            <Text style={[s.tabTxt, on && { color: C.brandDark }]}>{t.name}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// The MediSafe mark: a rounded square with a cross and a small leaf-shaped tick in the corner.
// light: white square with a teal cross, for dark backgrounds.
export const Logo = ({ size = 34, light }) => {
  const box = light ? '#fff' : C.brand;
  const mark = light ? C.brand : '#fff';
  return (
    <View style={{ width: size, height: size, borderRadius: size * 0.3, backgroundColor: box, alignItems: 'center', justifyContent: 'center' }}>
      <View style={{ position: 'absolute', width: size * 0.2, height: size * 0.56, borderRadius: size * 0.07, backgroundColor: mark }} />
      <View style={{ position: 'absolute', width: size * 0.56, height: size * 0.2, borderRadius: size * 0.07, backgroundColor: mark }} />
      <View style={{ position: 'absolute', right: size * 0.12, top: size * 0.12, width: size * 0.16, height: size * 0.16,
                     borderRadius: size * 0.08, backgroundColor: light ? C.mint : C.mint }} />
    </View>
  );
};

// Round profile picture: the user's photo, or initials, or a plain person icon.
export function Avatar({ photo, sex, name, size = 40, light }) {
  if (photo) return <Image source={{ uri: photo }} style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: C.soft }} />;
  const initials = (name || '').trim().split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: light ? 'rgba(255,255,255,0.16)' : C.tint,
                   alignItems: 'center', justifyContent: 'center' }}>
      {initials ? <Text style={{ fontSize: size * 0.36, fontWeight: '800', color: light ? '#fff' : C.brandDark }}>{initials}</Text>
        : <Icon name={sex === 'female' ? 'woman' : sex === 'male' ? 'man' : 'person'} size={size * 0.55} color={light ? '#fff' : C.brandDark} />}
    </View>
  );
}

export const Card = ({ children, style }) => <View style={[s.card, style]}>{children}</View>;

// Small uppercase heading above a group of cards.
export const SectionLabel = ({ children, style }) => <Text style={[T.label, s.section, style]}>{children}</Text>;

// One row in a white list card: icon, label, value, optional chevron.
export function ListRow({ icon, label, value, onPress, last, color = C.brand, chevron }) {
  const Box = onPress ? Pressable : View;
  return (
    <Box onPress={onPress} style={[s.row, !last && s.rowLine]} {...(onPress ? { accessibilityRole: 'button' } : {})}>
      {icon ? <View style={[s.rowIcon, { backgroundColor: color + '16' }]}><Icon name={icon} size={18} color={color} /></View> : null}
      <Text style={s.rowLabel}>{label}</Text>
      {value !== undefined ? <Text style={s.rowValue}>{value}</Text> : <View style={{ flex: 1 }} />}
      {chevron || onPress ? <Icon name="chevron-forward" size={18} color={C.faint} /> : null}
    </Box>
  );
}

export const IconCircle = ({ name, color = C.brand, bg = C.tint, size = 44 }) => (
  <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: bg, alignItems: 'center', justifyContent: 'center' }}>
    <Icon name={name} size={size * 0.5} color={color} />
  </View>
);

// Tap to open / close. Keeps long details out of the way until someone wants them.
export function Accordion({ icon, color = C.brand, title, summary, children, open: startOpen = false }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <View style={s.acc}>
      <Pressable onPress={() => setOpen(o => !o)} style={s.accHead} accessibilityRole="button"
        accessibilityState={{ expanded: open }}>
        <IconCircle name={icon} color={color} bg={color + '18'} size={40} />
        <View style={{ flex: 1 }}>
          <Text style={T.h3}>{title}</Text>
          {summary ? <Text style={T.small} numberOfLines={1}>{summary}</Text> : null}
        </View>
        <Icon name={open ? 'chevron-up' : 'chevron-down'} size={22} color={C.faint} />
      </Pressable>
      {open ? <View style={s.accBody}>{children}</View> : null}
    </View>
  );
}

// Segmented control: one row of options, one selected. Used in forms.
export function Segmented({ options, value, onChange }) {
  return (
    <View style={s.seg} accessibilityRole="radiogroup">
      {options.map(o => {
        const on = o.value === value;
        return (
          <Pressable key={String(o.value)} onPress={() => onChange(o.value)} style={[s.segItem, on && s.segOn]}
            accessibilityRole="radio" accessibilityState={{ selected: on }}>
            <Text style={[s.segTxt, on && { color: C.brandDark }]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// Small coloured result label: ok | caution | stop
export function Chip({ status, label }) {
  const st = STATUS[status];
  return (
    <View style={[s.chip, { backgroundColor: st.bg }]}>
      <Icon name={st.icon} size={15} color={st.color} />
      <Text style={[s.chipTxt, { color: st.color }]}>{label}</Text>
    </View>
  );
}

// Coloured message: kind = ok | caution | stop | info
export function Notice({ kind, title, children, icon }) {
  const st = STATUS[kind];
  return (
    <View style={[s.notice, { backgroundColor: st.bg }]}>
      <Icon name={icon || st.icon} size={22} color={st.color} />
      <View style={{ flex: 1 }}>
        {title ? <Text style={[T.h3, { color: st.color, marginBottom: 2 }]}>{title}</Text> : null}
        {typeof children === 'string' ? <Text style={[T.body, { fontSize: 15, lineHeight: 22 }]}>{children}</Text> : children}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root:     { flex: 1 },
  bar:      { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 8, minHeight: 56 },
  largeBar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingTop: 12, paddingBottom: 10 },
  side:     { minWidth: 72 },
  back:     { width: 40, height: 40, borderRadius: 20, backgroundColor: C.soft, alignItems: 'center', justifyContent: 'center' },
  barTitle: { fontSize: 17, fontWeight: '700', color: C.ink },
  dots:     { flexDirection: 'row', gap: 5, marginTop: 6 },
  dot:      { width: 8, height: 6, borderRadius: 3, backgroundColor: C.line },
  dotOn:    { backgroundColor: C.brand },
  content:  { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 32 },
  footer:   { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 12, gap: 8, borderTopWidth: 1, borderTopColor: C.line },
  btn:      { minHeight: 54, borderRadius: 16, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 20 },
  btnSmall: { minHeight: 44, borderRadius: 12 },
  btnTxt:   { fontSize: 16, fontWeight: '700', letterSpacing: 0.2 },
  card:     { backgroundColor: '#fff', borderRadius: 18, padding: 18, borderWidth: 1, borderColor: C.line },
  section:  { marginTop: 22, marginBottom: 8, marginLeft: 4 },
  row:      { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 13, minHeight: 54 },
  rowLine:  { borderBottomWidth: 1, borderBottomColor: C.line },
  rowIcon:  { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  rowLabel: { fontSize: 15, color: C.sub },
  rowValue: { flex: 1, fontSize: 15, fontWeight: '600', color: C.ink, textAlign: 'right' },
  acc:      { backgroundColor: '#fff', borderRadius: 18, marginBottom: 12, borderWidth: 1, borderColor: C.line },
  accHead:  { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16, minHeight: 72 },
  accBody:  { paddingHorizontal: 18, paddingBottom: 18 },
  seg:      { flexDirection: 'row', backgroundColor: C.soft, borderRadius: 14, padding: 4, gap: 4 },
  segItem:  { flex: 1, minHeight: 44, borderRadius: 11, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 },
  segOn:    { backgroundColor: '#fff', ...shadow },
  segTxt:   { fontSize: 15, fontWeight: '700', color: C.sub },
  chip:     { flexDirection: 'row', alignItems: 'center', gap: 4, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 4, alignSelf: 'flex-start' },
  chipTxt:  { fontSize: 13, fontWeight: '700' },
  tabs:     { flexDirection: 'row', borderTopWidth: 1, borderTopColor: C.line, backgroundColor: '#fff', paddingTop: 8 },
  tab:      { flex: 1, alignItems: 'center', gap: 2 },
  tabPill:  { width: 56, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  tabTxt:   { fontSize: 12, fontWeight: '600', color: C.faint },
  notice:   { flexDirection: 'row', gap: 12, borderRadius: 16, padding: 14, marginBottom: 12 },
});
