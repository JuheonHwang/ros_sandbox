// 토픽 지연 측정용 talker (C++ 컴포넌트). latency_lab/latency.py의 Talker와 같은 측정을 한다.
#include <chrono>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_components/register_node_macro.hpp"
#include "sensor_msgs/msg/image.hpp"

namespace ipc_lab
{

class Talker : public rclcpp::Node
{
public:
  // 컴포넌트는 반드시 NodeOptions 하나를 받는 생성자가 있어야 한다.
  // 컨테이너가 use_intra_process_comms 같은 설정을 이 options로 넘겨준다.
  explicit Talker(const rclcpp::NodeOptions & options)
  : Node("ipc_talker", options)
  {
    size_ = declare_parameter("size", 1024);  // payload bytes
    const double rate = declare_parameter("rate", 100.0);
    const int depth = declare_parameter("depth", 10);
    // QoS(depth) = KEEP_LAST(depth), RELIABLE, VOLATILE. intra-process는 KEEP_LAST만 허용한다.
    pub_ = create_publisher<sensor_msgs::msg::Image>("latency_test", rclcpp::QoS(depth));
    timer_ = create_wall_timer(std::chrono::duration<double>(1.0 / rate), [this] {tick();});
    RCLCPP_INFO(
      get_logger(), "publishing %ld bytes at %.1f Hz (intra-process: %s)", size_, rate,
      get_node_options().use_intra_process_comms() ? "on" : "off");
  }

private:
  void tick()
  {
    // 매번 새 메시지를 만든다. publish(unique_ptr)는 소유권을 넘기는 것이라
    // 보낸 뒤에는 이 메시지를 다시 쓸 수 없기 때문이다(Python 버전처럼 재사용 불가).
    auto msg = std::make_unique<sensor_msgs::msg::Image>();
    msg->height = 1;
    msg->width = msg->step = size_;
    msg->encoding = "mono8";
    msg->data.resize(size_);
    msg->header.frame_id = std::to_string(++seq_);  // 유실 계산용 일련번호(실습용, 실제 코드에선 금지)
    if (seq_ == 1) {
      // listener가 찍는 주소와 같으면 "복사 없이 같은 메모리를 넘겨받았다(zero-copy)"는 증거
      RCLCPP_INFO(
        get_logger(), "seq=1 data addr=%p", static_cast<const void *>(msg->data.data()));
    }
    // stamp는 publish 직전에: 메시지 할당 시간은 빼고 "통신"만 재기 위해
    msg->header.stamp = now();
    // unique_ptr로 넘겨야 intra-process에서 복사 없이 전달될 수 있다.
    // (const 참조로 publish하면 rclcpp가 내부에서 한 번 복사한다)
    pub_->publish(std::move(msg));
  }

  int64_t size_;
  int64_t seq_ = 0;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace ipc_lab

RCLCPP_COMPONENTS_REGISTER_NODE(ipc_lab::Talker)
