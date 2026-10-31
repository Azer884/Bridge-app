import { ActivityIndicator, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { createNavigationContainerRef, DefaultTheme, NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator, type NativeStackNavigationOptions } from "@react-navigation/native-stack";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useFonts, PublicSans_400Regular, PublicSans_500Medium, PublicSans_600SemiBold, PublicSans_700Bold, PublicSans_800ExtraBold } from "@expo-google-fonts/public-sans";
import { api, configureApi } from "../shared/api";
import ApproveScreen from "./src/screens/ApproveScreen";
import CalendarScreen from "./src/screens/CalendarScreen";
import CustomersScreen from "./src/screens/CustomersScreen";
import LinkScreen from "./src/screens/LinkScreen";
import PersonasScreen from "./src/screens/PersonasScreen";
import PipelineScreen from "./src/screens/PipelineScreen";
import QuoteDetailScreen from "./src/screens/QuoteDetailScreen";
import QuotesScreen from "./src/screens/QuotesScreen";
import SettingsScreen from "./src/screens/SettingsScreen";
import StatusScreen from "./src/screens/StatusScreen";
import { useAsync } from "./src/hooks";
import { ActorProvider } from "./src/actor";
import { customerOf, refreshPush, setBadge, useTappedNotification } from "./src/push";
import { C, F, ThemeProvider, useTheme } from "./src/theme";

configureApi({
  baseUrl: process.env.EXPO_PUBLIC_API_URL ?? "",
  apiKey: process.env.EXPO_PUBLIC_API_KEY,
  mock: process.env.EXPO_PUBLIC_USE_MOCK !== "false",
  bookingsLive: process.env.EXPO_PUBLIC_BOOKINGS_LIVE === "true",
});

const Tabs = createBottomTabNavigator();
const navigation = createNavigationContainerRef<any>();
const Approve = createNativeStackNavigator();
const Jobs = createNativeStackNavigator();
const More = createNativeStackNavigator();

/** Large titles on iOS, standard headers elsewhere. Colors are read fresh so a theme change repaints. */
const header = (): NativeStackNavigationOptions => ({
  headerLargeTitle: true,
  headerShadowVisible: false,
  headerLargeTitleShadowVisible: false,
  headerStyle: { backgroundColor: C.wall },
  headerLargeStyle: { backgroundColor: C.wall },
  headerTintColor: C.blue,
  headerTitleStyle: { color: C.ink, fontFamily: F.semi },
  headerLargeTitleStyle: { color: C.ink, fontFamily: F.display, fontSize: 34 },
  contentStyle: { backgroundColor: C.wall },
});

const detail = ({ route }: { route: { params?: object } }): NativeStackNavigationOptions => ({
  title: (route.params as { name?: string } | undefined)?.name ?? "Quote",
  headerLargeTitle: false,
});

/** Screens every tab can open: a quote to review, and the calendar to book it. */
const shared = (Stack: typeof Approve) => (
  <>
    <Stack.Screen name="QuoteDetail" component={QuoteDetailScreen} options={detail} />
    <Stack.Screen name="Calendar" component={CalendarScreen} options={{ title: "Calendar", headerLargeTitle: false }} />
  </>
);

function ApproveStack() {
  useTheme();
  return (
    <Approve.Navigator screenOptions={header()}>
      <Approve.Screen name="ApproveHome" component={ApproveScreen} options={{ title: "Approve" }} />
      {shared(Approve)}
    </Approve.Navigator>
  );
}
function JobsStack() {
  useTheme();
  return (
    <Jobs.Navigator screenOptions={header()}>
      <Jobs.Screen name="JobsHome" component={QuotesScreen} options={{ title: "Jobs" }} />
      {shared(Jobs)}
    </Jobs.Navigator>
  );
}
function MoreStack() {
  useTheme();
  return (
    <More.Navigator screenOptions={header()}>
      <More.Screen name="MoreHome" component={SettingsScreen} options={{ title: "More" }} />
      <More.Screen name="Pipeline" component={PipelineScreen} options={{ title: "Pipeline", headerLargeTitle: false }} />
      <More.Screen name="Customers" component={CustomersScreen} options={{ title: "Customers", headerLargeTitle: false }} />
      <More.Screen name="Link" component={LinkScreen} options={{ title: "WhatsApp number", headerLargeTitle: false }} />
      <More.Screen name="Personas" component={PersonasScreen} options={{ title: "Personas", headerLargeTitle: false }} />
      <More.Screen name="Status" component={StatusScreen} options={{ title: "Status", headerLargeTitle: false }} />
      {shared(More)}
    </More.Navigator>
  );
}

const icon = (on: keyof typeof Ionicons.glyphMap, off: keyof typeof Ionicons.glyphMap) =>
  ({ color, focused }: { color: string; focused: boolean }) => <Ionicons name={focused ? on : off} size={24} color={color} />;

export default function App() {
  return (
    <ThemeProvider>
      <ActorProvider>
        <Root />
      </ActorProvider>
    </ThemeProvider>
  );
}

function Root() {
  const { mode } = useTheme();
  const [loaded] = useFonts({ PublicSans_400Regular, PublicSans_500Medium, PublicSans_600SemiBold, PublicSans_700Bold, PublicSans_800ExtraBold });
  const waiting = useAsync(
    async () => (await api.listQuotes("pending_approval")).length + (await api.listQuotes("needs_inspection")).length,
    [],
    20_000,
  );
  const tapped = useTappedNotification();
  const count = waiting.data ?? 0;

  useEffect(() => { void refreshPush(); }, []);
  useEffect(() => setBadge(count), [count]);
  useEffect(() => {
    // a tapped notification opens that customer's quote, ready to approve
    const who = customerOf(tapped ?? null);
    if (who && navigation.isReady()) {
      navigation.navigate("ApproveTab", { screen: "QuoteDetail", params: { userId: who.userId, name: who.name } });
    }
  }, [tapped]);

  if (!loaded) {
    return (
      <View style={{ flex: 1, backgroundColor: C.wall, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={C.blue} />
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style={mode === "dark" ? "light" : "dark"} />
      <NavigationContainer ref={navigation} theme={{ ...DefaultTheme, dark: mode === "dark", colors: { ...DefaultTheme.colors, background: C.wall, card: C.paper, text: C.ink, border: C.line, primary: C.blue } }}>
        <Tabs.Navigator
          screenOptions={{
            headerShown: false,
            tabBarActiveTintColor: C.blue,
            tabBarInactiveTintColor: C.ink3,
            tabBarStyle: { backgroundColor: C.paper, borderTopColor: C.line },
            tabBarLabelStyle: { fontFamily: F.semi, fontSize: 11 },
            tabBarBadgeStyle: { backgroundColor: C.blue, color: "#FFFFFF" },
          }}
        >
          <Tabs.Screen name="ApproveTab" component={ApproveStack} options={{ title: "Approve", tabBarIcon: icon("checkmark-circle", "checkmark-circle-outline"), tabBarBadge: count > 0 ? count : undefined }} />
          <Tabs.Screen name="JobsTab" component={JobsStack} options={{ title: "Jobs", tabBarIcon: icon("briefcase", "briefcase-outline") }} />
          <Tabs.Screen name="MoreTab" component={MoreStack} options={{ title: "More", tabBarIcon: icon("ellipsis-horizontal-circle", "ellipsis-horizontal-circle-outline") }} />
        </Tabs.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}