// Edit profile (Formik). Name, date of birth, gender, women's health, medicines, other supplements and health conditions.
// Everything starts filled in from the saved profile, so the user only changes what they want.
// Also used once for older accounts that have no profile yet (route param `next` = where to go after saving),
// and by guests (route param `guest`): no name, and the details are kept on this phone only.
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { Formik } from 'formik';
import * as Yup from 'yup';
import { Screen, Button, Notice, Icon, SectionLabel, C, T } from '../ui';
import { Field, DobField, Choice, HealthFields, HEALTH_RULES, PERIOD_OPTIONS, dobToIso, isoToDob, ageFrom, splitList, joinList } from '../forms';
import { getProfile, getMedicines, saveProfile, isGuest, errorMessage } from '../api';
import { auth } from '../firebase';

const NAME = /^[A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF .'-]{1,39}$/;
// Age from the date of birth; older accounts saved only an age, so fall back to that.
const age = v => (dobToIso(v.dob) ? ageFrom(dobToIso(v.dob)) : v._age ?? null);
// Women's health questions: shown for females (age unknown counts as "ask")
const asksPeriods = v => v.sex === 'female' && (age(v) == null || age(v) >= 8);
const asksPregnancy = v => v.sex === 'female' && (age(v) == null || (age(v) >= 12 && age(v) <= 55 && !(age(v) >= 35 && v.periods === 'no')));

const schema = guest => Yup.object({
  name: guest ? Yup.string().nullable()
    : Yup.string().trim().required('Enter your name.').matches(NAME, 'Letters and spaces only, 2-40 characters.'),
  // only needed when no age is saved yet; if typed, it must be a real date
  dob: Yup.string().nullable()
    .test('needed', 'Enter your date of birth.', function (v) { return !!v || this.parent._age != null; })
    .test('real', 'Enter a real date as DD/MM/YYYY.', v => !v || !!dobToIso(v))
    .test('range', 'Age must be between 1 and 120.', v => !dobToIso(v) || (ageFrom(dobToIso(v)) >= 1 && ageFrom(dobToIso(v)) <= 120)),
  sex: Yup.string().nullable().required('Choose one.'),
  periods: Yup.string().nullable().test('asked', 'Choose one.', function (v) { return !asksPeriods(this.parent) || !!v; }),
  pregnant: Yup.boolean().nullable().test('asked', 'Choose one.', function (v) { return !asksPregnancy(this.parent) || v !== null; }),
  breastfeeding: Yup.boolean().nullable().test('asked', 'Choose one.', function (v) { return !asksPregnancy(this.parent) || v !== null; }),
  ...HEALTH_RULES,
});

export default function EditProfileScreen({ route, navigation }) {
  const next = route.params?.next;
  const guest = !!route.params?.guest || isGuest();
  const [start, setStart] = useState(null);
  const [medicines, setMedicines] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    getMedicines().then(setMedicines).catch(() => setMedicines([]));
    getProfile().then(p => setStart({
      name: p?.name || auth.currentUser?.displayName || '',
      dob: isoToDob(p?.dob), _age: p?.dob ? null : (p?.age ?? null), sex: p?.sex || null, periods: p?.periods || null,
      pregnant: p?.pregnant ?? null, breastfeeding: p?.breastfeeding ?? null, medicines: p?.medicines || [],
      otherMedicines: joinList(p?.other_medicines), otherSupplements: joinList(p?.other_supplements),
      conditions: joinList(p?.conditions),
    }));
  }, []);

  const save = async (v, { setSubmitting }) => {
    setError(null);
    try {
      const dob = dobToIso(v.dob);
      await saveProfile({
        name: (v.name || '').trim(), sex: v.sex, ...(dob ? { dob } : { age: v._age }),
        periods: asksPeriods(v) ? v.periods : null,
        pregnant: asksPregnancy(v) ? !!v.pregnant : false, breastfeeding: asksPregnancy(v) ? !!v.breastfeeding : false,
        medicines: v.medicines, other_medicines: splitList(v.otherMedicines),
        other_supplements: splitList(v.otherSupplements), conditions: splitList(v.conditions),
      });
      next ? navigation.reset({ index: 0, routes: [{ name: next }] }) : navigation.goBack();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (!start) return <Screen title="Edit profile" onBack={() => navigation.goBack()}><ActivityIndicator color={C.brand} style={{ marginTop: 40 }} /></Screen>;

  return (
    <Formik initialValues={start} validationSchema={schema(guest)} onSubmit={save}>
      {form => {
        const { values, errors, touched, handleChange, handleBlur, setFieldValue, handleSubmit, isSubmitting } = form;
        const err = k => touched[k] && errors[k];
        return (
          <Screen title={next ? '' : 'Edit profile'} onBack={next && !guest ? undefined : () => navigation.goBack()} bg={C.soft}
            footer={<Button label={next ? 'Continue' : 'Save'} icon={next ? 'arrow-forward' : 'checkmark'} onPress={handleSubmit} loading={isSubmitting} />}>
            {next ? (
              <View style={s.intro}>
                <Text style={T.title}>{guest ? 'A few details first' : 'Your health profile'}</Text>
                <Text style={[T.sub, { marginTop: 6 }]}>We use these to check if a supplement and its dose are right for you.</Text>
                {guest ? (
                  <View style={s.private}>
                    <Icon name="phone-portrait-outline" size={16} color={C.brandDark} />
                    <Text style={[T.small, { flex: 1, color: C.brandDark }]}>Kept on this phone only. Create an account any time to save your reports.</Text>
                  </View>
                ) : null}
              </View>
            ) : null}

            {!guest ? <>
              <SectionLabel>Account</SectionLabel>
              <View style={s.card}>
                <Field label="Full name" icon="person-outline" value={values.name} onChangeText={handleChange('name')}
                  onBlur={handleBlur('name')} autoCapitalize="words" error={err('name')} />
              </View>
            </> : null}

            <SectionLabel>About you</SectionLabel>
            <View style={s.card}>
              <DobField value={values.dob} onChange={v => setFieldValue('dob', v)} error={err('dob')} />
              <Choice label="Gender" value={values.sex} onChange={v => setFieldValue('sex', v)} error={err('sex')}
                options={[{ value: 'male', label: 'Male' }, { value: 'female', label: 'Female' }]} />
            </View>

            {asksPeriods(values) && <>
              <SectionLabel>Women's health</SectionLabel>
              <View style={s.card}>
                <Choice label="Periods" value={values.periods} onChange={v => setFieldValue('periods', v)}
                  error={err('periods')} options={PERIOD_OPTIONS} />
                {asksPregnancy(values) && <>
                  <Choice label="Are you pregnant?" value={values.pregnant} onChange={v => setFieldValue('pregnant', v)}
                    error={err('pregnant')} options={[{ value: false, label: 'No' }, { value: true, label: 'Yes' }]} />
                  <Choice label="Are you breastfeeding?" value={values.breastfeeding} onChange={v => setFieldValue('breastfeeding', v)}
                    error={err('breastfeeding')} options={[{ value: false, label: 'No' }, { value: true, label: 'Yes' }]} />
                </>}
              </View>
            </>}

            <SectionLabel>Medicines, supplements and conditions</SectionLabel>
            <View style={s.card}>
              <HealthFields form={form} medicines={medicines} err={err} />
            </View>

            {error ? <View style={{ marginTop: 12 }}><Notice kind="stop">{error}</Notice></View> : null}
          </Screen>
        );
      }}
    </Formik>
  );
}

const s = StyleSheet.create({
  intro:   { marginBottom: 4, marginTop: 4 },
  private: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.tint, borderRadius: 12, padding: 12, marginTop: 14 },
  card:    { backgroundColor: '#fff', borderRadius: 18, borderWidth: 1, borderColor: C.line, padding: 16, gap: 16 },
});
