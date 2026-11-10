using UnityEngine;

public class PhotoSensor : MonoBehaviour
{
    public float range = 0.75f;
    public Color onColor = Color.red;
    public Color offColor = Color.gray;

    public bool detected;
    public int xNo = -1; // 연결할 입력 번호 (-1 이면 연결 안함)

    private Renderer rend;
    private bool lastDetected;

    public bool defectOnly;


    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        rend = GetComponent<Renderer>();
        if(rend != null) rend.material.color = offColor;
    }

    // Update is called once per frame
    void FixedUpdate()
    {
        // 센서 위치에서 아래(-Y) 방향으로 레이를 쏨 
        detected = false;
        

        if (Physics.Raycast(transform.position, Vector3.down, out RaycastHit hit, range))
        {
            //맞은 물체가 Box 태그일 떄만 감지
            if (hit.collider.CompareTag("Box"))
            {
                if (defectOnly)
                {   //맞은 물체가 불량일떄 감지
                    BoxItem item = hit.collider.GetComponent<BoxItem>();
                    detected = item != null && item.isDefective;
                }
                else
                {
                    detected = true;
                }
            }
            
        }

        if (detected != lastDetected)
        {
            if(rend !=null) rend.material.color = detected ? onColor : offColor;
            Debug.Log(name + (detected ? "ON" : "OFF"));
            lastDetected = detected;
        }

        if (xNo >= 0 && PlcIo.Instance != null) PlcIo.Instance.X[xNo] = detected;
    }

    void OnDrawGizmos()
    {
        Gizmos.color = detected ? Color.red : Color.green;
        Gizmos.DrawLine(transform.position, transform.position + Vector3.down * range);
    }
    
   
}
