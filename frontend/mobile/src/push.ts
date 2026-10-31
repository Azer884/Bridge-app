import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { api, apiMode } from "../../shared/api";

/** Show a notification even while the app is open: the owner should not miss a customer who is waiting. */
Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: true }),
});

export type PushState = "on" | "off" | "denied" | "unsupported";

/** Push only works on a real phone talking to the live backend. */
const supported = () => apiMode() !== "mock" && Device.isDevice;

export async function pushState(): Promise<PushState> {
  if (!supported()) return "unsupported";
  try {
    const { status } = await Notifications.getPermissionsAsync();
    return status === "granted" ? "on" : status === "denied" ? "denied" : "off";
  } catch {
    return "unsupported";
  }
}

async function register(): Promise<void> {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "Quotes to approve", importance: Notifications.AndroidImportance.HIGH, vibrationPattern: [0, 250, 250, 250],
    });
  }
  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  const { data } = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
  await api.registerPush(data, Platform.OS);
}

/** Called from a button, so the permission prompt appears when the owner knows why. */
export async function enableNotifications(): Promise<PushState> {
  if (!supported()) return "unsupported";
  try {
    let { status } = await Notifications.getPermissionsAsync();
    if (status !== "granted") ({ status } = await Notifications.requestPermissionsAsync());
    if (status !== "granted") return "denied";
    await register();
    return "on";
  } catch {
    return "off";
  }
}

/** On launch: refresh this phone's push address if the owner already said yes. Never asks. */
export async function refreshPush(): Promise<void> {
  if ((await pushState()) === "on") await register().catch(() => {});
}

/** The red number on the app icon: quotes waiting for a decision. */
export const setBadge = (n: number) => void Notifications.setBadgeCountAsync(n).catch(() => {});

/** The notification the owner tapped, if any. Browsers have no notifications, so the web preview gets nothing. */
export const useTappedNotification: () => Notifications.NotificationResponse | null | undefined =
  Platform.OS === "web" ? () => null : Notifications.useLastNotificationResponse;

/** The customer a tapped notification is about, if any. */
export function customerOf(response: Notifications.NotificationResponse | null): { userId: string; name?: string } | null {
  const data = response?.notification.request.content.data as { user_id?: string; name?: string } | undefined;
  return data?.user_id ? { userId: data.user_id, name: data.name } : null;
}