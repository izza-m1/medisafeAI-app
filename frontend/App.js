// Splash → Welcome (try as a guest, sign in or sign up) → Home ⇄ History ⇄ Profile (bottom tabs) → Scan or Search → Confirm → Reasons → Report
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import SplashScreen from './screens/SplashScreen';
import WelcomeScreen from './screens/WelcomeScreen';
import SignInScreen from './screens/SignInScreen';
import SignUpScreen from './screens/SignUpScreen';
import HomeScreen from './screens/HomeScreen';
import HistoryScreen from './screens/HistoryScreen';
import ProfileScreen from './screens/ProfileScreen';
import EditProfileScreen from './screens/EditProfileScreen';
import ScanScreen from './screens/ScanScreen';
import SearchScreen from './screens/SearchScreen';
import ConfirmScreen from './screens/ConfirmScreen';
import ReasonsScreen from './screens/ReasonsScreen';
import ReportScreen from './screens/ReportScreen';

const Stack = createNativeStackNavigator();
const TAB = { animation: 'none', gestureEnabled: false };            // Home, History and Profile switch instantly, like tabs

export default function App() {
  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <Stack.Navigator initialRouteName="Splash" screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Splash" component={SplashScreen} />
          <Stack.Screen name="Welcome" component={WelcomeScreen} options={{ animation: 'fade' }} />
          <Stack.Screen name="SignIn" component={SignInScreen} />
          <Stack.Screen name="SignUp" component={SignUpScreen} />
          <Stack.Screen name="Home" component={HomeScreen} options={TAB} />
          <Stack.Screen name="History" component={HistoryScreen} options={TAB} />
          <Stack.Screen name="Profile" component={ProfileScreen} options={TAB} />
          <Stack.Screen name="EditProfile" component={EditProfileScreen} />
          <Stack.Screen name="Scan" component={ScanScreen} />
          <Stack.Screen name="Search" component={SearchScreen} />
          <Stack.Screen name="Confirm" component={ConfirmScreen} />
          <Stack.Screen name="Reasons" component={ReasonsScreen} />
          <Stack.Screen name="Report" component={ReportScreen} />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
