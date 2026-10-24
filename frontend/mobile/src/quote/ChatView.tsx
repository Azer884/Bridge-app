import { useState } from "react";
import { Image, Linking, Modal, Pressable, ScrollView, useWindowDimensions, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api, explainError } from "../../../shared/api";
import { phone } from "../../../shared/format";
import type { ChatMessage, Photo } from "../../../shared/types";
import { C, F } from "../theme";
import { Banner, Btn, Field, Group, Row, T, success } from "../ui";

const time = (iso: string) => new Date(iso).toLocaleString("en-MY", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const WHO = { customer: "Customer", assistant: "Gesir", owner: "You" } as const;

/** Photos from the backend are real images. If one cannot be drawn, show its caption instead of a blank. */
function Thumb({ p, w, h, onPress }: { p: Photo; w: number; h: number; onPress: () => void }) {
  const [bad, setBad] = useState(false);
  return (
    <Pressable accessibilityRole="imagebutton" accessibilityLabel={`Open photo: ${p.caption}`} onPress={onPress} style={{ width: w, height: h, borderRadius: 10, overflow: "hidden", backgroundColor: C.chip }}>
      {bad ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 6, gap: 4 }}>
          <Ionicons name="image-outline" size={24} color={C.ink3} />
          <T v="foot" numberOfLines={2} style={{ textAlign: "center" }}>{p.caption}</T>
        </View>
      ) : (
        <Image source={{ uri: p.url }} style={{ width: w, height: h }} resizeMode="cover" onError={() => setBad(true)} accessibilityLabel={p.caption} />
      )}
    </Pressable>
  );
}

export function PhotoViewer({ photos, index, onClose }: { photos: Photo[]; index: number; onClose: () => void }) {
  const [i, setI] = useState(index);
  const [zoom, setZoom] = useState(1);
  const [bad, setBad] = useState(false);
  const { width, height } = useWindowDimensions();
  const p = photos[i];
  const go = (d: number) => { setI((v) => (v + d + photos.length) % photos.length); setZoom(1); setBad(false); };
  const btn = { width: 44, height: 44, alignItems: "center" as const, justifyContent: "center" as const };

  return (
    <Modal visible animationType="fade" onRequestClose={onClose} statusBarTranslucent>
      <View style={{ flex: 1, backgroundColor: "#020A10" }}>
        <View style={{ flexDirection: "row", alignItems: "center", paddingTop: 48, paddingHorizontal: 8, gap: 4 }}>
          <Pressable accessibilityRole="button" accessibilityLabel="Close photo" onPress={onClose} style={btn}><Ionicons name="close" size={26} color="#EAF1F1" /></Pressable>
          <View style={{ flex: 1 }}>
            <T numberOfLines={1} style={{ color: "#EAF1F1" }}>{p.caption}</T>
            <T v="foot" style={{ color: "#9DB5BD" }}>{i + 1} of {photos.length}</T>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Zoom out" disabled={zoom <= 1} onPress={() => setZoom((z) => Math.max(1, z - 0.5))} style={[btn, { opacity: zoom <= 1 ? 0.4 : 1 }]}><Ionicons name="remove-circle-outline" size={26} color="#EAF1F1" /></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Zoom in" disabled={zoom >= 4} onPress={() => setZoom((z) => Math.min(4, z + 0.5))} style={[btn, { opacity: zoom >= 4 ? 0.4 : 1 }]}><Ionicons name="add-circle-outline" size={26} color="#EAF1F1" /></Pressable>
        </View>
        <ScrollView horizontal maximumZoomScale={4} minimumZoomScale={1} contentContainerStyle={{ alignItems: "center" }} style={{ flex: 1 }}>
          <ScrollView maximumZoomScale={4} contentContainerStyle={{ justifyContent: "center", minHeight: height - 140 }}>
            {bad ? (
              <View style={{ width, alignItems: "center", padding: 32 }}><T style={{ color: "#EAF1F1" }}>{p.caption}</T></View>
            ) : (
              <Image source={{ uri: p.url }} style={{ width: width * zoom, height: width * zoom * 0.75 }} resizeMode="contain" onError={() => setBad(true)} accessibilityLabel={p.caption} />
            )}
          </ScrollView>
        </ScrollView>
        {photos.length > 1 && (
          <View style={{ flexDirection: "row", justifyContent: "space-between", padding: 16, paddingBottom: 32 }}>
            <Pressable accessibilityRole="button" accessibilityLabel="Previous photo" onPress={() => go(-1)} style={btn}><Ionicons name="chevron-back" size={28} color="#EAF1F1" /></Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Next photo" onPress={() => go(1)} style={btn}><Ionicons name="chevron-forward" size={28} color="#EAF1F1" /></Pressable>
          </View>
        )}
      </View>
    </Modal>
  );
}

interface ChatProps {
  name: string;
  number: string;
  chat: ChatMessage[];
  photos: Photo[];
  userId: string;
  needsHuman?: boolean;
  humanActive?: boolean;
  onSent: () => void;
}

export function ChatView({ name, number, chat, photos, userId, needsHuman, humanActive, onSent }: ChatProps) {
  const [open, setOpen] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function send() {
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await api.sendOwnerMessage(userId, text.trim());
      success();
      setText("");
      onSent();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  async function resume() {
    try {
      await api.resumeAssistant(userId);
      onSent();
    } catch (e) {
      setErr(e);
    }
  }
  const idx = new Map(photos.map((p, i) => [p.id, i]));
  const { width } = useWindowDimensions();
  const cell = Math.floor((width - 32 - 16) / 3);

  return (
    <>
      <Group>
        <Row title={name} subtitle={phone(number)} right={<Btn small kind="tinted" label="WhatsApp" icon="logo-whatsapp" onPress={() => Linking.openURL(`https://wa.me/${number.replace(/\D/g, "")}`)} />} />
      </Group>

      <View style={{ gap: 8, backgroundColor: C.chip, borderRadius: 16, padding: 12 }} accessibilityRole="summary" accessibilityLabel="WhatsApp conversation">
        {chat.length === 0 ? <T v="sub">No messages yet.</T> : null}
        {chat.map((m) => {
          const mine = m.role !== "customer";
          return (
            <View key={m.id} style={{ alignItems: mine ? "flex-end" : "flex-start" }}>
              <View style={{ maxWidth: "86%", padding: 10, gap: 4, borderRadius: 16, borderBottomRightRadius: mine ? 4 : 16, borderBottomLeftRadius: mine ? 16 : 4, backgroundColor: m.role === "assistant" ? "#D9FDD3" : m.role === "owner" ? C.blueWash : C.paper }}>
                <T v="foot" style={{ fontFamily: F.semi, color: m.role === "assistant" ? "#2F6B4C" : C.ink3 }}>{WHO[m.role]}</T>
                <T style={{ color: m.role === "assistant" ? "#041B2D" : C.ink }}>{m.text}</T>
                {m.photo_ids?.length ? (
                  <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
                    {m.photo_ids.map((id) => {
                      const i = idx.get(id);
                      return i != null ? <Thumb key={id} p={photos[i]} w={110} h={82} onPress={() => setOpen(i)} /> : null;
                    })}
                  </View>
                ) : null}
                <T v="foot" style={{ alignSelf: "flex-end", color: m.role === "assistant" ? "#4B6B5A" : C.ink3 }}>{time(m.ts)}</T>
              </View>
            </View>
          );
        })}
      </View>

      {needsHuman && !humanActive ? <Banner kind="warn" text={`The assistant asked for a person. Write to ${name} below.`} /> : null}
      {humanActive ? <Banner kind="info" text={`You are replying by hand, so the assistant is paused for ${name}.`} action="Let the assistant continue" onAction={resume} /> : null}
      <Group title="Reply on WhatsApp" footer="Sent from your number in place of the assistant. It stays quiet for 30 minutes after.">
        <View style={{ padding: 12, gap: 10 }}>
          <Field label={`Message to ${name}`} multiline maxLength={1000} placeholder="Write a message" value={text} onChangeText={setText} style={{ minHeight: 84, textAlignVertical: "top" }} />
          {err != null ? <Banner text={explainError(err)} /> : null}
          <Btn label="Send" busy={busy} disabled={!text.trim()} onPress={send} />
        </View>
      </Group>

      <View style={{ gap: 8 }}>
        <T v="label" style={{ paddingHorizontal: 16 }}>Photos from the customer</T>
        {photos.length === 0 ? (
          <T v="sub" style={{ paddingHorizontal: 16 }}>The customer has not sent any photos.</T>
        ) : (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {photos.map((p, i) => <Thumb key={p.id} p={p} w={cell} h={Math.round(cell * 0.75)} onPress={() => setOpen(i)} />)}
          </View>
        )}
      </View>
      {open != null && <PhotoViewer photos={photos} index={open} onClose={() => setOpen(null)} />}
    </>
  );
}
