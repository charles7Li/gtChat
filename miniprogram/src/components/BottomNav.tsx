import Taro from "@tarojs/taro";
import { Text, View } from "@tarojs/components";

const items = [
  { id: "home", label: "首页", url: "/pages/home/index" },
  { id: "jobs", label: "任务", url: "/pages/jobs/index" },
  { id: "reports", label: "报告", url: "/pages/reports/index" },
  { id: "profile", label: "我的", url: "/pages/profile/index" }
];

export function BottomNav({ active }: { active: string }) {
  return (
    <View className="bottom-nav">
      {items.map((item) => (
        <View
          key={item.id}
          className={`bottom-nav__item ${active === item.id ? "is-active" : ""}`}
          onClick={() => active !== item.id && Taro.reLaunch({ url: item.url })}
        >
          <Text className="bottom-nav__mark" />
          <Text>{item.label}</Text>
        </View>
      ))}
    </View>
  );
}

