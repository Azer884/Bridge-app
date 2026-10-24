import { ActivityIndicator, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import { DefaultTheme, NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator, type NativeStackNavigationOptions } from "@react-navigation/native-stack";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useFonts, BarlowCondensed_700Bold } from "@expo-google-fonts/barlow-condensed";
import { api, configureApi } from "../shared/api";
import CalendarScreen from "./src/screens/CalendarScreen";
import LinkScreen from "./src/screens/LinkScreen";
import PersonasScreen from "./src/screens/PersonasScreen";
import PipelineScreen from "./src/screens/PipelineScreen";
import QuoteDetailScreen from "./src/screens/QuoteDetailScreen";
import QuotesScreen from "./src/screens/QuotesScreen";
import SettingsScreen from "./src/screens/SettingsScreen";
import StatusScreen from "./src/screens/StatusScreen";
import { useAsync } from "./src/hooks";
import { C, F, ThemeProvider, useTheme } from "./src/theme";
import { ThemeButton } from "./src/ui";

configureApi({
  baseUrl: process.env.EXPO_PUBLIC_API_URL ?? "",
  apiKey: process.env.EXPO_PUBLIC_API_KEY,
  mock: process.env.EXPO_PUBLIC_USE_MOCK !== "false",
  bookingsLive: process.env.EXPO_PUBLIC_BOOKINGS_LIVE === "true",
});

const Tabs = createBottomTabNavigator();
const Quotes = createNativeStackNavigator();
const Pipeline = createNativeStackNavigator();
const Calendar = createNativeStackNavigator();
const Settings = createNativeStackNavigator();

/** Large titles on iOS, standard headers elsewhere. Colors are read fresh so a theme change repaints. */
const header = (): NativeStackNavigationOptions => ({
  headerLargeTitle: true,
  headerShadowVisible: false,
  headerLargeTitleShadowVisible: false,
  headerStyle: { backgroundColor: C.wall },
  headerLargeStyle: { backgroundColor: C.wall },
  headerTintColor: C.blue,
  headerTitleStyle: { color: C.ink, fontFamily: F.sys },
  headerLargeTitleStyle: { color: C.ink, fontFamily: F.display, fontSize: 38 },
  contentStyle: { backgroundColor: C.wall },
  headerRight: () => <ThemeButton />,
});

const detail = ({ route }: { route: { params?: object } }): NativeStackNavigationOptions => ({
  title: (route.params as { name?: string } | undefined)?.name ?? "Quote",
  headerLargeTitle: false,
});

function QuotesStack() {
  useTheme();
  return (
    <Quotes.Navigator screenOptions={header()}>
      <Quotes.Screen name="QuotesHome" component={QuotesScreen} options={{ title: "Quotes" }} />
      <Quotes.Screen name="QuoteDetail" component={QuoteDetailScreen} options={detail} />
    </Quotes.Navigator>
  );
}
function PipelineStack() {
  useTheme();
  return (
    <Pipeline.Navigator screenOptions={header()}>
      <Pipeline.Screen name="PipelineHome" component={PipelineScreen} options={{ title: "Pipeline" }} />
      <Pipeline.Screen name="QuoteDetail" component={QuoteDetailScreen} options={detail} />
    </Pipeline.Navigator>
  );
}
function CalendarStack() {
  useTheme();
  return (
    <Calendar.Navigator screenOptions={header()}>
      <Calendar.Screen name="CalendarHome" component={CalendarScreen} options={{ title: "Calendar" }} />
    </Calendar.Navigator>
  );
}
function SettingsStack() {
  useTheme();
  return (
    <Settings.Navigator screenOptions={header()}>
      <Settings.Screen name="SettingsHome" component={SettingsScreen} options={{ title: "Settings" }} />
      <Settings.Screen name="Link" component={LinkScreen} options={{ title: "WhatsApp number" }} />
      <Settings.Screen name="Personas" component={PersonasScreen} options={{ title: "Personas" }} />
      <Settings.Screen name="Status" component={StatusScreen} options={{ title: "Status" }} />
    </Settings.Navigator>
  );
}

const icon = (on: keyof typeof Ionicons.glyphMap, off: keyof typeof Ionicons.glyphMap) =>
  ({ color, focused }: { color: string; focused: boolean }) => <Ionicons name={focused ? on : off} size={24} color={color} />;

export default function App() {
  return (
    <ThemeProvider>
      <Root />
    </ThemeProvider>
  );
}

function Root() {
  const { mode } = useTheme();
  const [loaded] = useFonts({ BarlowCondensed_700Bold });
  const pending = useAsync(() => api.listQuotes("pending_approval"), [], 20_000);

  if (!loaded) {
    return (
      <View style={{ flex: 1, backgroundColor: C.wall, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={C.blue} />
      </View>
    );
  }
  const count = pending.data?.length ?? 0;

  return (
    <SafeAreaProvider>
      <StatusBar style={mode === "dark" ? "light" : "dark"} />
      <NavigationContainer theme={{ ...DefaultTheme, dark: mode === "dark", colors: { ...DefaultTheme.colors, background: C.wall, card: C.paper, text: C.ink, border: C.line, primary: C.blue } }}>
        <Tabs.Navigator
          screenOptions={{
            headerShown: false,
            tabBarActiveTintColor: C.blue,
            tabBarInactiveTintColor: C.ink3,
            tabBarStyle: { backgroundColor: C.paper, borderTopColor: C.line },
            tabBarLabelStyle: { fontFamily: F.sys, fontSize: 11, fontWeight: "600" },
            tabBarBadgeStyle: { backgroundColor: C.tape, color: "#041B2D" },
          }}
        >
          <Tabs.Screen name="QuotesTab" component={QuotesStack} options={{ title: "Quotes", tabBarIcon: icon("document-text", "document-text-outline"), tabBarBadge: count > 0 ? count : undefined }} />
          <Tabs.Screen name="PipelineTab" component={PipelineStack} options={{ title: "Pipeline", tabBarIcon: icon("albums", "albums-outline") }} />
          <Tabs.Screen name="CalendarTab" component={CalendarStack} options={{ title: "Calendar", tabBarIcon: icon("calendar", "calendar-outline") }} />
          <Tabs.Screen name="SettingsTab" component={SettingsStack} options={{ title: "Settings", tabBarIcon: icon("settings", "settings-outline") }} />
        </Tabs.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}

