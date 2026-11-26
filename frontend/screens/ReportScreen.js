// The safety report. Order: verdict with a short summary (tap a check for its details), Ask MediSafe, how to take
// it, your reasons, foods and drinks, other supplements, about the supplement. Every fact opens its NIH source, and
// the whole report can be saved or shared as a PDF.
import React, { useEffect, useState } from 'react';
import { View, Text, Image, Pressable, StyleSheet, ActivityIndicator, Linking, TextInput, Modal, ScrollView } from 'react-native';
import { Screen, Button, Chip, Icon, IconCircle, Accordion, STATUS, C, T } from '../ui';
import { api, errorMessage, describeProfile, healthDetails, askQuestion, cachedProfile } from '../api';
import { LinkText } from '../forms';
import { downloadReportPdf, shareReportPdf, pairText, uncheckedText } from '../reportPdf';

const VERDICT = {
  'Safe':             { status: 'ok',      title: 'Safe for you' },
  'Use with caution': { status: 'caution', title: 'Take with care' },
  'Not safe':         { status: 'stop',    title: 'Not safe for you' },
};
const CHECK_LABEL = { ok: 'OK', caution: 'Check', stop: 'Not suitable', info: 'Check pack' };
const ORDER = { stop: 0, caution: 1, info: 2, ok: 3 };
const REASON = { helps: ['ok', 'Helps'], no: ['stop', "Won't help"], unsure: ['stop', 'Not proven'] };
const PUBLISHER = { 'NIH Office of Dietary Supplements': 'NIH ODS', 'NIH NCCIH': 'NIH NCCIH' };
const PAIR = { raises: 'ok', lowers: 'caution', take_apart: 'caution' };
const SUMMARY_FOODS = 3;

// AI items are {text, sources}; reports saved by older versions have plain strings.
const textOf = item => (typeof item === 'string' ? item : item?.text || '');
const sourcesOf = item => (typeof item === 'string' ? [] : item?.sources || []);
const shortName = food => food.split(' (')[0].split(' / ')[0];

// What happens while the report is made, ticked off one by one
const PREP = ['Your age, sex and health', 'Dose against the NIH limits', 'Your medicines and conditions',
  'Foods and other supplements', 'AI pharmacist checking the NIH fact sheets'];
function Preparing({ name }) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStage(i => Math.min(i + 1, PREP.length - 1)), 1800);
    return () => clearInterval(t);
  }, []);
  return (
    <View style={s.prep} accessibilityLiveRegion="polite">
      <Text style={T.title}>Preparing your report</Text>
      <Text style={[T.sub, { marginTop: 4, marginBottom: 18 }]}>Checking {name} for you.</Text>
      {PREP.map((step, i) => (
        <View key={step} style={s.prepRow}>
          {i < stage ? <Icon name="checkmark-circle" size={22} color={C.safe} />
            : i === stage ? <ActivityIndicator size="small" color={C.brand} style={{ width: 22 }} />
            : <Icon name="ellipse-outline" size={22} color={C.line} />}
          <Text style={[T.body, { color: i <= stage ? C.ink : C.faint, fontWeight: i === stage ? '600' : '400' }]}>{step}</Text>
        </View>
      ))}
      <Text style={[T.small, { marginTop: 16 }]}>This can take up to a minute.</Text>
    </View>
  );
}

const Section = ({ icon, title, children }) => (
  <View style={{ marginTop: 22 }}>
    <View style={s.sectionHead}>
      <View style={s.secIcon}><Icon name={icon} size={18} color={C.brand} /></View>
      <Text style={s.sectionTitle}>{title}</Text>
    </View>
    <View style={s.sheet}>{children}</View>
  </View>
);

// The NIH passages an AI sentence is based on, as small pills: tap one to open that fact sheet.
function Citations({ sources, numbered }) {
  if (!sources?.length) return null;
  return (
    <View style={s.pills}>
      {sources.map((src, i) => (
        <Pressable key={src.id + i} onPress={() => Linking.openURL(src.url)} style={s.citePill}
          accessibilityRole="link" accessibilityLabel={`Source: ${src.title}, ${src.publisher}`}>
          <Icon name="document-text-outline" size={13} color={C.brandDark} />
          <Text style={s.citeTxt} numberOfLines={1}>
            {numbered ? `${i + 1}. ` : ''}{PUBLISHER[src.publisher] || src.publisher} · {src.title.split(' - ').slice(1).join(', ') || src.title}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

// The exact NIH sentences behind a fact, with a link to each fact sheet.
const Quotes = ({ items }) => (items || []).map((w, i) => (
  <View key={i} style={{ marginTop: i ? 14 : 4 }}>
    {w.text ? <Text style={T.body}>{w.text}</Text> : null}
    {(w.quotes || []).map((q, j) => (
      <View key={j} style={s.quote}>
        <Text style={[T.small, { fontStyle: 'italic', color: C.ink }]}>"{q.text}"</Text>
        <LinkText onPress={() => Linking.openURL(q.url)} style={s.source}>NIH ODS: {q.section}</LinkText>
      </View>
    ))}
  </View>
));

// One popup for every "tap for details": a safety check, or the NIH facts behind a food or a timing.
function Details({ item, onClose }) {
  if (!item) return null;
  const st = item.status ? STATUS[item.status] : null;
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.backdrop} onPress={onClose} accessibilityLabel="Close" />
      <View style={s.sheetModal}>
        <View style={s.grabber} />
        <View style={s.modalHead}>
          {st ? <Icon name={st.icon} size={24} color={st.color} /> : <Icon name="document-text" size={22} color={C.brand} />}
          <Text style={[T.h2, { flex: 1 }]}>{item.title}</Text>
          {st ? <Text style={[s.checkTag, { color: st.color }]}>{item.tag}</Text> : null}
        </View>
        <ScrollView style={{ maxHeight: 420 }} contentContainerStyle={{ paddingBottom: 8 }}>
          {item.text ? <Text style={[T.body, { marginTop: 6 }]}>{item.text}</Text> : null}
          {item.ai ? <View style={[s.inline, { marginTop: 8 }]}><Icon name="sparkles" size={14} color={C.brandDark} /><Text style={s.aiTag}>Found by the AI pharmacist in the NIH fact sheets</Text></View> : null}
          <Citations sources={item.citations} />
          <Quotes items={item.why} />
          {item.source?.startsWith?.('http') ? <LinkText onPress={() => Linking.openURL(item.source)} style={[s.source, { marginTop: 10 }]}>Open the source</LinkText> : null}
        </ScrollView>
        <Button label="Close" kind="secondary" onPress={onClose} />
      </View>
    </Modal>
  );
}

// The whole report in a few lines, at the top: what to watch, when to take it, what to keep apart.
function Summary({ r, checks, red }) {
  const watch = checks.filter(c => c.status === 'stop' || c.status === 'caution').map(c => c.title);
  const lower = (r.foods_to_avoid || []).map(f => shortName(f.food));
  const lines = [
    watch.length ? ['alert-circle', C.caution, `Check: ${watch.join(', ')}`] : null,
    !red && r.timing ? ['restaurant', C.brandDark, r.timing.text] : null,
    !red && lower.length ? ['remove-circle', C.danger, `Not with: ${lower.slice(0, SUMMARY_FOODS).join(', ')}${lower.length > SUMMARY_FOODS ? ` and ${lower.length - SUMMARY_FOODS} more` : ''}`] : null,
    !red && r.other_supplements?.length ? ['git-compare', C.brandDark, pairText(r.other_supplements[0])] : null,
  ].filter(Boolean);
  if (!lines.length) return null;
  return (
    <View style={s.summary}>
      {lines.map(([icon, color, text]) => (
        <View key={text} style={s.summaryRow}>
          <Icon name={icon} size={18} color={color} />
          <Text style={[T.sub, { flex: 1, color: C.ink }]}>{text}</Text>
        </View>
      ))}
    </View>
  );
}

function Nutrient({ n, last }) {
  const pct = n.percent_of_need;
  const color = n.over_limit ? C.danger : C.brand;
  const label = pct == null ? '' : pct >= 200 ? `${Math.round(pct / 100)} times your daily need` : `${pct}% of your daily need`;
  return (
    <View style={[s.nutrient, !last && s.lineBorder]}>
      <View style={{ flexDirection: 'row' }}>
        <Text style={[T.body, { flex: 1 }]}>{n.nutrient}</Text>
        <Text style={[T.h3, { color }]}>{n.per_tablet}</Text>
      </View>
      {pct != null && <View style={s.track}><View style={[s.fill, { width: `${Math.min(pct, 100)}%`, backgroundColor: color }]} /></View>}
      <Text style={[T.small, n.over_limit && { color: C.danger, fontWeight: '700' }]}>
        {label}{label ? '. ' : ''}{n.safe_limit.startsWith('No') ? 'No upper limit set.' : `Safe limit ${n.safe_limit} a day.`}
      </Text>
    </View>
  );
}

// One everyday food and the nutrients in this product it helps or lowers; tap for the NIH facts.
function FoodRow({ f, verb, color, onOpen, last }) {
  return (
    <Pressable onPress={() => onOpen({ title: f.food, why: f.why })} style={[s.foodRow, !last && s.foodLine]}
      accessibilityRole="button" accessibilityHint="Shows the NIH facts">
      <View style={[s.foodDot, { backgroundColor: color }]} />
      <View style={{ flex: 1 }}>
        <Text style={s.foodName}>{f.food}</Text>
        {f.nutrients?.length ? <Text style={T.small}>{verb} {f.nutrients.join(', ')}</Text> : null}
      </View>
      <Icon name="chevron-forward" size={18} color={C.faint} />
    </Pressable>
  );
}

// A question about this supplement, answered only from the NIH fact sheets, with numbered sources.
function AskMediSafe({ scanId, name, profile, suggestions }) {
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState([]);              // [{ question, answer, sources, covered }]
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const send = async (typed) => {
    const q = (typeof typed === 'string' ? typed : question).trim();
    if (q.length < 3 || busy) return;
    setBusy(true); setError(null);
    try {
      const out = await askQuestion(scanId, name, q, profile);
      setAsked(list => [...list, { question: q, ...out }]);
      setQuestion('');
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <View>
      <Text style={T.sub}>Answers come only from the NIH fact sheets, with their sources.</Text>
      {!asked.length && suggestions?.length ? (
        <View style={[s.pills, { marginTop: 10 }]}>
          {suggestions.map(q => (
            <Pressable key={q} onPress={() => send(q)} style={s.suggest} accessibilityRole="button" disabled={busy}>
              <Text style={s.suggestTxt}>{q}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      {asked.map((a, i) => (
        <View key={i} style={s.qa}>
          <Text style={T.h3}>{a.question}</Text>
          <Text style={[T.body, { marginTop: 4, color: a.covered ? C.ink : C.sub }]}>{a.answer}</Text>
          <Citations sources={a.sources} numbered />
        </View>
      ))}
      <View style={s.askRow}>
        <TextInput style={s.askInput} value={question} onChangeText={setQuestion} placeholder={`Ask about ${name}`}
          placeholderTextColor={C.faint} maxLength={300} onSubmitEditing={send} returnKeyType="send" />
        <Pressable onPress={send} style={s.askBtn} accessibilityRole="button" accessibilityLabel="Ask">
          {busy ? <ActivityIndicator size="small" color="#fff" /> : <Icon name="send" size={18} color="#fff" />}
        </Pressable>
      </View>
      {busy ? <Text style={[T.small, { marginTop: 6 }]}>Searching the NIH fact sheets...</Text> : null}
      {error ? <Text style={[T.small, { color: C.danger, marginTop: 6 }]}>{error}</Text> : null}
    </View>
  );
}

// Questions to start with, made from this report: a food it lists, the person's own situation, side effects.
function suggestedQuestions(r, person) {
  const food = [...(r.foods_to_avoid || []), ...(r.recommended_foods || [])].map(f => f.food)[0];
  return [
    food ? `Can I take it with ${shortName(food).toLowerCase()}?` : null,
    person?.pregnant ? 'Is it safe during pregnancy?' : person?.breastfeeding ? 'Is it safe while breastfeeding?' : null,
    person?.medicine_names?.length ? `Is it okay with ${person.medicine_names[0]}?` : null,
    'What side effects should I watch for?',
  ].filter(Boolean).slice(0, 3);
}

export default function ReportScreen({ route, navigation }) {
  const { savedId, scan, name } = route.params;         // savedId: opening a past check from History
  const [data, setData]       = useState(null);
  const [error, setError]     = useState(null);
  const [details, setDetails] = useState(null);       // what the popup shows
  const [saving, setSaving]   = useState(false);

  const load = async () => {
    setError(null); setData(null);
    try {
      if (savedId) {
        setData((await api.get(`/report/${savedId}`)).data);
      } else {
        const { profile, reasons } = route.params;
        setData((await api.post('/safety-report', { scan_id: scan.scan_id, supplement_name: name, reasons, ...healthDetails(profile) })).data);
      }
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  useEffect(() => { load(); }, []);

  const again = () => navigation.reset({ index: 1, routes: [{ name: 'Home' }, { name: 'Scan' }] });
  // PDF: kind = 'download' (save to a folder on the phone) or 'share' (WhatsApp, email...)
  const pdf = async kind => {
    setSaving(kind);
    try {
      const me = await cachedProfile();
      if (kind === 'share') return await shareReportPdf(data, me?.name);
      const out = await downloadReportPdf(data, me?.name);
      if (out.saved) setDetails({ title: 'Report downloaded', status: 'ok', text: `Saved as ${out.file} in ${out.folder}.` });
    } catch (e) {
      setDetails({ title: "Couldn't make the PDF", text: e?.message || 'Please try again.' });
    } finally {
      setSaving(null);
    }
  };

  if (!data) {
    return (
      <Screen title="Safety report" step={savedId ? null : 3} onBack={() => navigation.goBack()} bg={C.soft}
        footer={error ? <>
          <Button label="Scan another pack" icon="camera" onPress={again} />
          <Button label="Try again" kind="ghost" small onPress={load} />
        </> : null}>
        {error ? (
          <View style={s.loading}>
            <IconCircle name="document-text" size={84} color={C.caution} bg={C.cautionBg} />
            <Text style={[T.title, { textAlign: 'center' }]}>We can't make this report</Text>
            <Text style={[T.sub, { textAlign: 'center' }]}>{error}</Text>
          </View>
        ) : savedId ? (
          <View style={s.loading}>
            <ActivityIndicator size="large" color={C.brand} />
            <Text style={[T.sub, { textAlign: 'center' }]}>Opening your saved report.</Text>
          </View>
        ) : <Preparing name={name} />}
      </Screen>
    );
  }

  const r = data.report;
  const person = data.profile;
  const reasons = data.reasons || [];
  const photo = route.params.photo || data.thumb;
  const v = VERDICT[r.is_safe_to_take.verdict];
  const tone = r.is_safe_to_take.tone || v.status;
  const st = STATUS[tone];
  const dose = r.recommended_dosage || {};
  const sum = dose.summary || {};
  const purpose = r.purpose_check?.results || [];
  const made = r.is_safe_to_take.checks.find(c => c.key === 'maker');
  const checks = r.is_safe_to_take.checks.filter(c => c.key !== 'maker').sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const red = tone === 'stop';                         // not safe, or not for your reason: no dose or food advice
  const openCheck = c => setDetails({ title: c.title, status: c.status, tag: CHECK_LABEL[c.status], text: c.text,
    ai: c.ai, citations: c.citations, source: c.ai ? null : c.source });

  return (
    <Screen title="Safety report" step={savedId ? null : 3} onBack={() => navigation.goBack()} bg={C.soft}
      footer={
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <View style={{ flex: 1 }}><Button label="Download PDF" icon="download-outline" onPress={() => pdf('download')} loading={saving === 'download'} /></View>
          <Pressable onPress={() => pdf('share')} disabled={!!saving} style={({ pressed }) => [s.share, pressed && { opacity: 0.8 }]}
            accessibilityRole="button" accessibilityLabel="Share the PDF">
            {saving === 'share' ? <ActivityIndicator color={C.brandDark} /> : <Icon name="share-social-outline" size={22} color={C.brandDark} />}
          </Pressable>
          <Pressable onPress={again} style={({ pressed }) => [s.share, pressed && { opacity: 0.8 }]}
            accessibilityRole="button" accessibilityLabel="Scan another supplement">
            <Icon name="scan-outline" size={22} color={C.brandDark} />
          </Pressable>
        </View>
      }>

      {/* Report header */}
      <View style={s.sheet}>
        <View style={s.reportHead}>
          {photo ? <Image source={{ uri: photo }} style={s.photo} /> : <View style={[s.photo, s.photoEmpty]}><Icon name="medical" size={26} color={C.brand} /></View>}
          <View style={{ flex: 1 }}>
            <Text style={s.kicker}>SUPPLEMENT SAFETY REPORT</Text>
            <Text style={T.title}>{data.product.name}</Text>
            <View style={[s.inline, { marginTop: 4 }]}>
              <Text style={[T.small, { flexShrink: 1 }]}>{data.company.name || 'Maker not seen on the pack'}</Text>
              {made ? <Chip status={made.status} label={{ ok: 'Official maker', caution: 'Check maker', info: 'Not verified', stop: 'Check maker' }[made.status]} /> : null}
            </View>
          </View>
        </View>
        <Text style={[T.small, { marginTop: 10 }]}>Checked for: {describeProfile(person)}{reasons.length ? ` · For: ${reasons.join(', ')}` : ''}</Text>
      </View>

      {/* Verdict: the answer, a short summary of the whole report, and every check as a button */}
      <View style={[s.verdict, { backgroundColor: st.bg, borderColor: st.color }]}>
        <View style={s.inline}>
          <Icon name={st.icon} size={40} color={st.color} />
          <Text style={[s.verdictTitle, { color: st.color, flex: 1 }]}>{r.is_safe_to_take.title || v.title}</Text>
        </View>
        <Text style={[T.body, { marginTop: 10 }]}>{r.is_safe_to_take.reason}</Text>
        <Citations sources={r.is_safe_to_take.summary_sources} />
        <Summary r={r} checks={checks} red={red} />
        <Text style={[s.label, { marginTop: 14 }]}>TAP A CHECK FOR DETAILS</Text>
        <View style={s.glance}>
          {checks.map((c, i) => (
            <Pressable key={c.key + i} onPress={() => openCheck(c)} style={[s.glanceItem, { borderColor: STATUS[c.status].color }]}
              accessibilityRole="button" accessibilityLabel={`${c.title}: ${CHECK_LABEL[c.status]}`}>
              <Icon name={c.ai ? 'sparkles' : STATUS[c.status].icon} size={16} color={STATUS[c.status].color} />
              <Text style={s.glanceTxt}>{c.title}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      {/* Ask MediSafe: only right after a scan, while the scan is still on the server */}
      {!savedId && scan ? (
        <Section icon="chatbubbles" title="Ask MediSafe">
          <AskMediSafe scanId={scan.scan_id} name={name} profile={route.params.profile} suggestions={suggestedQuestions(r, person)} />
        </Section>
      ) : null}

      {red ? null : (
        <Section icon="time" title="How to take it">
          {sum.doctor_only ? (
            <View style={[s.alert, { backgroundColor: C.dangerBg, borderColor: C.danger }]}>
              <Icon name="medkit" size={24} color={C.danger} />
              <Text style={[T.h3, { color: C.danger, flex: 1 }]}>Only take this if your doctor prescribed it.</Text>
            </View>
          ) : (
            <>
              <View style={s.tiles}>
                {[['ellipse', 'Amount', sum.amount || 'As on the pack'], ['repeat', 'How often', sum.how_often || 'As on the pack']].map(([icon, label, value]) => (
                  <View key={label} style={s.tile}>
                    <Icon name={icon} size={18} color={C.brand} />
                    <Text style={T.small}>{label}</Text>
                    <Text style={s.tileValue}>{value}</Text>
                  </View>
                ))}
              </View>
              <Pressable disabled={!r.timing} onPress={() => setDetails({ title: 'When to take it', why: r.timing?.why })}
                style={[s.alert, { backgroundColor: C.tint, borderColor: C.brand, marginTop: 10 }]} accessibilityRole="button">
                <Icon name="restaurant" size={20} color={C.brandDark} />
                <Text style={[T.body, { flex: 1, fontWeight: '600' }]}>{r.timing?.text || 'Follow the timing printed on the pack.'}</Text>
                {r.timing ? <Text style={s.why}>Why?</Text> : null}
              </Pressable>
              {(r.tips || []).map((t, i) => <Text key={i} style={[T.sub, { marginTop: 8 }]}>{t.text}</Text>)}
              {sum.short_course ? (
                <View style={[s.alert, { backgroundColor: C.cautionBg, borderColor: C.caution, marginTop: 10 }]}>
                  <Icon name="calendar" size={20} color={C.caution} />
                  <Text style={[T.sub, { color: C.ink, flex: 1 }]}><Text style={{ fontWeight: '800', color: C.caution }}>Short course only. </Text>Not for daily use over many months unless a doctor advises.</Text>
                </View>
              ) : null}
            </>
          )}
          {dose.nutrients?.length ? (
            <View style={{ marginTop: 14 }}>
              <Text style={s.label}>IN ONE TABLET</Text>
              {dose.nutrients.map((x, i) => <Nutrient key={x.nutrient} n={x} last={i === dose.nutrients.length - 1} />)}
            </View>
          ) : null}
        </Section>
      )}

      {purpose.length ? (
        <Section icon="help-circle" title="Does it help with your reason?">
          {purpose.map((p, i) => (
            <View key={p.reason} style={[s.reasonRow, i < purpose.length - 1 && s.lineBorder]}>
              <View style={s.inline}>
                <Icon name={STATUS[REASON[p.result][0]].icon} size={20} color={STATUS[REASON[p.result][0]].color} />
                <Text style={[T.h3, { flex: 1 }]}>{p.reason}</Text>
                <Text style={[s.checkTag, { color: STATUS[REASON[p.result][0]].color }]}>{REASON[p.result][1]}</Text>
              </View>
              <Text style={[T.sub, { marginTop: 4 }]}>{p.text}</Text>
            </View>
          ))}
          {r.purpose_check.ai_note ? <Text style={[T.sub, { marginTop: 10 }]}>{r.purpose_check.ai_note}</Text> : null}
          <Citations sources={r.purpose_check.ai_sources} />
        </Section>
      ) : null}

      {red ? null : <>
        <Section icon="nutrition" title="Foods and drinks">
          <Text style={[s.label, { color: C.danger }]}>CAN LOWER HOW MUCH YOU ABSORB</Text>
          {r.foods_to_avoid?.length ? r.foods_to_avoid.map((f, i) => (
            <FoodRow key={f.food} f={f} verb="Lowers" color={C.danger} onOpen={setDetails} last={i === r.foods_to_avoid.length - 1} />
          )) : <Text style={T.sub}>The NIH fact sheets name no food or drink that lowers how much of this you absorb.</Text>}
          <Text style={[s.label, { color: C.safe, marginTop: 16 }]}>HELPS YOU ABSORB IT</Text>
          {r.recommended_foods?.length ? r.recommended_foods.map((f, i) => (
            <FoodRow key={f.food} f={f} verb="Helps" color={C.safe} onOpen={setDetails} last={i === r.recommended_foods.length - 1} />
          )) : <Text style={T.sub}>The NIH fact sheets name no food that helps you absorb this.</Text>}
        </Section>

        {r.other_supplements?.length || r.unrecognised_supplements?.length ? (
          <Section icon="git-compare" title="With other supplements">
            {r.other_supplements.map((o, i) => {
              const ps = STATUS[PAIR[o.effect] || 'caution'];
              return (
                <Pressable key={o.id} onPress={() => setDetails({ title: 'With other supplements', why: [o] })}
                  style={[s.foodRow, i < r.other_supplements.length - 1 && s.foodLine]} accessibilityRole="button">
                  <Icon name={ps.icon} size={18} color={ps.color} />
                  <Text style={[T.body, { flex: 1 }]}>{pairText(o)}</Text>
                  <Icon name="chevron-forward" size={18} color={C.faint} />
                </Pressable>
              );
            })}
            {r.unrecognised_supplements?.length ? (
              <Text style={[T.sub, { marginTop: 8 }]}>{uncheckedText(r.unrecognised_supplements)}</Text>
            ) : null}
          </Section>
        ) : null}
      </>}

      <Section icon="book" title="About this supplement">
        {r.actual_usage ? (
          <View style={[s.aboutBox, { backgroundColor: C.tint }]}>
            <Text style={[s.label, { color: C.brandDark }]}>USED FOR</Text>
            <Text style={T.body}>{textOf(r.actual_usage)}</Text>
            <Citations sources={sourcesOf(r.actual_usage)} />
          </View>
        ) : null}
        {r.benefits?.length ? (
          <View style={s.aboutList}>
            <Text style={[s.label, { color: C.safe }]}>BENEFITS</Text>
            {r.benefits.map((t, i) => (
              <View key={i} style={s.aboutItem}><Icon name="checkmark-circle" size={18} color={C.safe} />
                <View style={{ flex: 1 }}><Text style={T.body}>{textOf(t)}</Text><Citations sources={sourcesOf(t)} /></View></View>
            ))}
          </View>
        ) : null}
        {r.side_effects?.length ? (
          <View style={s.aboutList}>
            <Text style={[s.label, { color: C.caution }]}>POSSIBLE SIDE EFFECTS</Text>
            {r.side_effects.map((t, i) => (
              <View key={i} style={s.aboutItem}><Icon name="alert-circle" size={18} color={C.caution} />
                <View style={{ flex: 1 }}><Text style={T.body}>{textOf(t)}</Text><Citations sources={sourcesOf(t)} /></View></View>
            ))}
          </View>
        ) : null}
        {r.notes?.map((t, i) => (
          <View key={i} style={s.aboutItem}><Icon name="information-circle" size={18} color={C.sub} /><Text style={[T.body, { flex: 1 }]}>{t}</Text></View>
        ))}
        {r.fact_sheets?.length ? (
          <View style={{ marginTop: 6 }}>
            <Accordion icon="library" title="NIH fact sheets" summary={`${r.fact_sheets.length} official fact sheet${r.fact_sheets.length > 1 ? 's' : ''} to read`}>
              {r.fact_sheets.map(f => (
                <LinkText key={f.url} onPress={() => Linking.openURL(f.url)} style={{ marginBottom: 8 }}>{f.nutrient}</LinkText>
              ))}
            </Accordion>
          </View>
        ) : null}
      </Section>

      <Text style={[T.small, { marginTop: 18, marginHorizontal: 4 }]}>
        From NIH Office of Dietary Supplements, NIH NCCIH and USDA data. The AI pharmacist only writes what it can cite
        from these. Follow the directions on the pack, or your doctor's advice.
      </Text>

      <Details item={details} onClose={() => setDetails(null)} />
    </Screen>
  );
}

const s = StyleSheet.create({
  share:       { width: 54, minHeight: 54, borderRadius: 16, backgroundColor: C.tint, alignItems: 'center', justifyContent: 'center' },
  loading:      { alignItems: 'center', gap: 16, paddingTop: 90 },
  prep:         { backgroundColor: '#fff', borderRadius: 14, borderWidth: 1, borderColor: C.line, padding: 20, marginTop: 20 },
  prepRow:      { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 },
  sheet:        { backgroundColor: '#fff', borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.line },
  reportHead:   { flexDirection: 'row', alignItems: 'center', gap: 14 },
  kicker:       { fontSize: 12, fontWeight: '800', letterSpacing: 1, color: C.brand, marginBottom: 2 },
  photo:        { width: 64, height: 64, borderRadius: 14, backgroundColor: C.soft },
  photoEmpty:   { alignItems: 'center', justifyContent: 'center', backgroundColor: C.tint },
  lineBorder:   { borderBottomWidth: 1, borderBottomColor: C.line },
  inline:       { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  verdict:      { borderRadius: 14, padding: 18, marginTop: 14, borderWidth: 1.5 },
  verdictTitle: { fontSize: 26, lineHeight: 31, fontWeight: '800' },
  summary:      { backgroundColor: 'rgba(255,255,255,0.85)', borderRadius: 12, padding: 12, marginTop: 12, gap: 8 },
  summaryRow:   { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  glance:       { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  glanceItem:   { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#fff', borderRadius: 999, borderWidth: 1,
                  paddingHorizontal: 12, paddingVertical: 8, minHeight: 40 },
  glanceTxt:    { fontSize: 14.5, fontWeight: '600', color: C.ink },
  sectionHead:  { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8, marginLeft: 2 },
  secIcon:      { width: 32, height: 32, borderRadius: 10, backgroundColor: C.tint, alignItems: 'center', justifyContent: 'center' },
  sectionTitle: { flex: 1, fontSize: 19, fontWeight: '800', color: C.ink },
  checkTag:     { fontSize: 13, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  alert:        { flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 14, borderWidth: 1, padding: 12 },
  why:          { fontSize: 14, fontWeight: '700', color: C.brand },
  tiles:        { flexDirection: 'row', gap: 8 },
  tile:         { flex: 1, backgroundColor: C.soft, borderRadius: 14, padding: 12, gap: 4 },
  tileValue:    { fontSize: 16, lineHeight: 21, fontWeight: '800', color: C.ink },
  foodRow:      { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, minHeight: 48 },
  foodLine:     { borderBottomWidth: 1, borderBottomColor: C.line },
  foodDot:      { width: 8, height: 8, borderRadius: 4 },
  foodName:     { fontSize: 16.5, fontWeight: '700', color: C.ink },
  reasonRow:    { paddingVertical: 12 },
  label:        { fontSize: 12, fontWeight: '800', letterSpacing: 1, color: C.sub, marginBottom: 6 },
  nutrient:     { paddingVertical: 10, gap: 6 },
  track:        { height: 8, borderRadius: 4, backgroundColor: C.line, overflow: 'hidden' },
  fill:         { height: '100%', borderRadius: 4 },
  aboutBox:     { borderRadius: 14, padding: 14, marginBottom: 10 },
  aboutList:    { marginTop: 8, marginBottom: 4 },
  aboutItem:    { flexDirection: 'row', gap: 10, alignItems: 'flex-start', marginBottom: 8, paddingTop: 2 },
  source:       { fontSize: 13, marginTop: 4 },
  aiTag:        { fontSize: 12, fontWeight: '700', color: C.brandDark },
  pills:        { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  citePill:     { flexDirection: 'row', alignItems: 'center', gap: 4, maxWidth: '100%', backgroundColor: 'rgba(255,255,255,0.85)',
                  borderRadius: 999, borderWidth: 1, borderColor: C.line, paddingHorizontal: 10, paddingVertical: 5 },
  citeTxt:      { fontSize: 12.5, fontWeight: '600', color: C.brandDark, flexShrink: 1 },
  quote:        { borderLeftWidth: 3, borderLeftColor: C.brand, paddingLeft: 10, marginTop: 8, gap: 2 },
  qa:           { borderTopWidth: 1, borderTopColor: C.line, paddingTop: 12, marginTop: 12 },
  suggest:      { borderWidth: 1.5, borderColor: C.brand, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8 },
  suggestTxt:   { fontSize: 14, fontWeight: '600', color: C.brandDark },
  askRow:       { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 14 },
  askInput:     { flex: 1, minHeight: 48, borderRadius: 12, borderWidth: 1.5, borderColor: C.line, paddingHorizontal: 14, fontSize: 16, color: C.ink, backgroundColor: '#fff' },
  askBtn:       { width: 48, height: 48, borderRadius: 12, backgroundColor: C.brand, alignItems: 'center', justifyContent: 'center' },
  backdrop:     { flex: 1, backgroundColor: 'rgba(15,23,42,0.45)' },
  sheetModal:   { backgroundColor: '#fff', borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 20, paddingBottom: 28, gap: 10 },
  grabber:      { alignSelf: 'center', width: 44, height: 5, borderRadius: 3, backgroundColor: C.line, marginBottom: 4 },
  modalHead:    { flexDirection: 'row', alignItems: 'center', gap: 10 },
});
