import { Text, View } from "@tarojs/components";

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <View className="empty-state">
      <Text className="empty-state__paw">· ᴥ ·</Text>
      <Text className="empty-state__title">{title}</Text>
      <Text className="empty-state__body">{body}</Text>
    </View>
  );
}

