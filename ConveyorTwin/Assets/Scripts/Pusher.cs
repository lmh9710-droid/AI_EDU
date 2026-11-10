using UnityEngine;
using UnityEngine.InputSystem;

public class Pusher : MonoBehaviour
{
    public int yExtend = 1; //전진 출력
    public int xRetracted = 4; //후진단 입력
    public int xExtended = 5; // 전진단 입력
    public bool extend; // 전진 명령 (나중에 PLC 출력 Y)
    public float stroke = 1.4f; // 스트로크(m)
    public float speed = 1.5f; // 속도(m/s)

    public bool isRetracted; //후진단 리드 스위치 (나중에 PLC 입니다.)
    public bool isExtended; //전진단 리드 스위치 (나중에 PLC 입니다.)

    private Rigidbody body;
    private Vector3 homePosition; // 후진 위치
    private float position; // 현재 위치 (0 ~ stroke)

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        body = GetComponent<Rigidbody>();
        homePosition = transform.position;
    }

    // Update is called once per frame
    void Update()
    {
        // 테스트용: P키로 전진/후진 전환 (6단계에서 PLC 로직으로 바뀜)
        if (Keyboard.current != null && Keyboard.current.pKey.wasPressedThisFrame)
        {
            extend = !extend;
        }
    }

    void FixedUpdate()
    {
        var io = PlcIo.Instance;
        if (io == null) return;

        extend = io.Y[yExtend]; // PLC 출력 읽기

        float target = extend ? stroke : 0f;
        position = Mathf.MoveTowards(position, target, speed * Time.fixedDeltaTime);
        body.MovePosition(homePosition + Vector3.forward * position);

        isRetracted = position <= 0.01f;
        isExtended = position >= stroke - 0.01f;

        io.X[xRetracted] = isRetracted;
        io.X[xExtended] = isExtended;
    }
}
 