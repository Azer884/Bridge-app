import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { api, apiMode } from "../../shared/api";

/** Show a notification even while the app is open: the owner should not miss a customer who is waiting. */
Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: true }),
});

/** Ask for permission once and give the backend this phone's push address. Quietly does nothing on a simulator,
 * with sample data, or when the owner says no. */
export async function registerForPush(): Promise<void> {
  if (apiMode() === "mock" || !Device.isDevice) return;
  try {
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Customers waiting", importance: Notifications.AndroidImportance.HIGH, vibrationPattern: [0, 250, 250, 250],
      });
    }
    let { status } = await Notifications.getPermissionsAsync();
    if (status !== "granted") ({ status } = await Notifications.requestPermissionsAsync());
    if (status !== "granted") return;
    const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
    const { data } = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
    await api.registerPush(data, Platform.OS);
  } catch {
    /* no push on this device: the badges in the app still show what is waiting */
  }
}

/** The customer a tapped notification is about, if any. */
export function customerOf(response: Notifications.NotificationResponse | null): { userId: string; name?: string } | null {
  const data = response?.notification.request.content.data as { user_id?: string; name?: string } | undefined;
  return data?.user_id ? { userId: data.user_id, name: data.name } : null;
}
