// 토픽 지연 측정용 listener (C++ 컴포넌트). latency_lab/latency.py의 Listener와 같은 측정을 한다.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>
#include <numeric>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_components/register_node_macro.hpp"
#include "sensor_msgs/msg/image.hpp"

namespace ipc_lab
{

using sensor_msgs::msg::Image;

class Listener : public rclcpp::Node
{
public:
  explicit Listener(const rclcpp::NodeOptions & options)
  : Node("ipc_listener", options)
  {
    const int depth = declare_parameter("depth", 10);
    // 콜백 인자를 UniquePtr로 받으면, intra-process에서 구독자가 하나일 때
    // 발행자가 넘긴 메시지를 복사 없이 그대로 받는다.
    sub_ = create_subscription<Image>(
      "latency_test", rclcpp::QoS(depth),
      [this](Image::UniquePtr msg) {on_msg(std::move(msg));});
    timer_ = create_wall_timer(std::chrono::seconds(1), [this] {report();});
  }

private:
  void on_msg(Image::UniquePtr msg)
  {
    // 콜백이 시작되자마자 now() - stamp: 06장의 ①~⑥ 전체가 이 값에 들어간다
    const double ms = (now() - rclcpp::Time(msg->header.stamp)).nanoseconds() / 1e6;
    const int64_t seq = std::stoll(msg->header.frame_id);
    if (last_seq_ < 0) {
      RCLCPP_INFO(
        get_logger(), "first msg seq=%ld data addr=%p", seq,
        static_cast<const void *>(msg->data.data()));
    } else if (seq > last_seq_ + 1) {
      lost_ += seq - last_seq_ - 1;
      total_lost_ += seq - last_seq_ - 1;
    }
    last_seq_ = seq;
    window_.push_back(ms);
    total_.push_back(ms);
  }

  void report()
  {
    if (window_.empty()) {
      RCLCPP_INFO(get_logger(), "waiting for messages...");
      return;
    }
    print("", window_, lost_);  // 최근 1초 창
    print("total ", total_, total_lost_);  // 시작부터 누적: 샘플이 많아 p99가 의미 있다
    window_.clear();
    lost_ = 0;
  }

  // ponytail: 매초 누적 표본 전체를 정렬(O(n log n)). 몇 분 실험엔 충분, 시간 단위면 히스토그램으로
  void print(const char * label, std::vector<double> s, int64_t lost)
  {
    std::sort(s.begin(), s.end());
    const size_t n = s.size();
    // nearest-rank 백분위수: 하위 q 비율을 덮는 가장 작은 값 (Python 버전과 동일)
    auto rank = [&](double q) {
        return s[std::max<size_t>(1, static_cast<size_t>(std::ceil(q * n))) - 1];
      };
    const double mean = std::accumulate(s.begin(), s.end(), 0.0) / n;
    RCLCPP_INFO(
      get_logger(), "%sn=%zu lost=%ld | latency ms: mean=%.3f p50=%.3f p99=%.3f max=%.3f",
      label, n, lost, mean, rank(0.50), rank(0.99), s.back());
  }

  int64_t last_seq_ = -1, lost_ = 0, total_lost_ = 0;
  std::vector<double> window_, total_;
  rclcpp::Subscription<Image>::SharedPtr sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace ipc_lab

RCLCPP_COMPONENTS_REGISTER_NODE(ipc_lab::Listener)
