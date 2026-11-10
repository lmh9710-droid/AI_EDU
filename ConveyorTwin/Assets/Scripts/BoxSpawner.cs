using UnityEngine;

public class BoxSpawner : MonoBehaviour
{
    public GameObject Boxprefab;//찍어낼 프리팹
    public float interval = 2.5f;
    public float lifeTime = 20f;
    
    private float timer = 0f;

    public Material defectMaterial; // 불량품 색
    [Range(0f, 1f)] public float defectRate = 0.3f; // 불량 비율 30% 

    // Update is called once per frame
    void Update()
    {
       
        timer += Time.deltaTime;

        if (timer >= interval)
        {

            bool occupied = Physics.CheckBox(transform.position, new Vector3(0.2f, 0.2f, 0.2f));
            if (occupied) return;
            timer = 0f;
            SpawnBox();
        }

    }

    void SpawnBox()
    {
        GameObject box = Instantiate(Boxprefab, transform.position, Quaternion.identity);
        box.name = "Box_" + Time.frameCount;

        if(Random.value < defectRate)
        {
            box.GetComponent<BoxItem>().isDefective = true;
            box.GetComponent<Renderer>().material = defectMaterial;
            box.name += "_NG";
        }

        Destroy(box, lifeTime);
    }
}
