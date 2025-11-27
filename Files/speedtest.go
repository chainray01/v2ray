import (
    "context"
    "fmt"
	"time"
    "github.com/xxf098/LiteSpeedTest/web"
)
 //测速
 //https://github.com/mahdibland/V2RayAggregator
 //https://github.com/xxf098/LiteSpeedTest
// see more details in ./examples
func testPing() error {
    ctx := context.Background()

    // 直接读取文件内容
    bytes, err := os.ReadFile("../data/All_Configs_base64_Sub.txt")
    if err != nil {
        return fmt.Errorf("cannot read subscription file: %v", err)
    }

    link := strings.TrimSpace(string(bytes))
    if link == "" {
        return fmt.Errorf("subscription content is empty")
    }
    opts := web.ProfileTestOptions{
		GroupName:     "Default", 
		SpeedTestMode: "pingonly",   //  pingonly speedonly all
		PingMethod:    "googleping", // googleping
		SortMethod:    "rspeed", // speed rspeed ping rping
		Concurrency:   2,
		TestMode:      2,
		Subscription:  link,
		Language:      "en",  // en cn
		FontSize:      24,
		Theme:         "rainbow",
        Unique:        true,
		Timeout:       10 * time.Second,
		OutputMode:  0,
	}
    nodes, err := web.TestContext(ctx, opts, &web.EmptyMessageWriter{})
    if err != nil {
        return err
    }
    // get all ok profile
    for _, node := range nodes {
        if node.IsOk {
			fmt.Println(node.Remarks)
		}
	}
    return nil
}