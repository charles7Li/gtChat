import { Text, View } from "@tarojs/components";

export function MarkdownView({ markdown }: { markdown: string }) {
  return (
    <View className="markdown">
      {markdown.split(/\r?\n/).map((line, index) => {
        if (!line.trim()) return <View className="markdown__space" key={index} />;
        if (line.startsWith("### ")) return <Text className="markdown__h3" key={index}>{line.slice(4)}</Text>;
        if (line.startsWith("## ")) return <Text className="markdown__h2" key={index}>{line.slice(3)}</Text>;
        if (line.startsWith("# ")) return <Text className="markdown__h1" key={index}>{line.slice(2)}</Text>;
        if (/^[-*] /.test(line)) return <Text className="markdown__bullet" key={index}>• {line.slice(2)}</Text>;
        return <Text className="markdown__p" key={index}>{line}</Text>;
      })}
    </View>
  );
}

