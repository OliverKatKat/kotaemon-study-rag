"""Download and pack the six published documents used in the acceptance tests."""

from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

UW = "https://courses.cs.washington.edu/courses/cse332/25sp/lecture/"
UTS = "https://wordpress-futures-prod.s3.ap-southeast-2.amazonaws.com/wp-content/uploads/"

SOURCES = {
    "11-hash2.pdf": (
        UW + "11-hash2.pdf",
        "7aa2d3679d6b02d8f0ba40d2f13173d47d754d94251853e9677f7974379d70fb",
    ),
    "11-hash2.pptx": (
        UW + "11-hash2.pptx",
        "8d92e93c417f68fd6998f3bf44eb6820085f91b4e5f826b83c7969162e7af318",
    ),
    "UTS-accessible-word.docx": (
        UTS + "2022/04/22132448/Microsoft-Word-document-example.docx",
        "a50b65b7c6ad181e37c67c5238f2a695eae732bdb458b53fc30738cee4e9fe0e",
    ),
    "USST-syllabus.docx": (
        "https://oece.usst.edu.cn/_upload/article/files/63/b4/"
        "c131eafb4db2979754f132dbd3c1/5264fb92-3254-41d2-b973-8f191782d8c5.docx",
        "09762a9cee7fcba698cd634a1bcf4ffeb4394a994133bedce6d852f49d2453bd",
    ),
    "UTS-accessible-powerpoint.pptx": (
        UTS + "2022/07/13093627/Accessible-content-practices-PPT-example-edited.pptx",
        "fc9571116d7b5deddf2029b7e8cec325c361cb061f433ae9bfe7be01f9bb2a4f",
    ),
    "USTC-ClassIn.pdf": (
        "https://www.teach.ustc.edu.cn/wp-content/uploads/2022/10/"
        "%E7%BA%BF%E4%B8%8A%E6%95%99%E5%AD%A6%E6%93%8D%E4%BD%9C%E8%AF%B4%E6%98%8E"
        "2022%E7%A7%8B-%E6%95%99%E5%B8%88%E7%80%9A%E6%B5%B7%E6%95%99%E5%AD%A6"
        "%E7%BD%91ClassIn.pdf",
        "ced8a509254b3386001657e89f57986a7902f4be6e5fa8c7c901ffc279bd857e",
    ),
}


def main():
    repo = Path(__file__).resolve().parents[1]
    output = repo / "downloads" / "real-samples"
    output.mkdir(parents=True, exist_ok=True)

    for name, (url, checksum) in SOURCES.items():
        path = output / name
        if path.is_file() and sha256(path.read_bytes()).hexdigest() == checksum:
            print(f"Verified {name}")
            continue
        request = Request(url, headers={"User-Agent": "Kotaemon study sample downloader"})
        with urlopen(request, timeout=60) as response:
            content = response.read()
        if sha256(content).hexdigest() != checksum:
            raise SystemExit(f"{name} differs from the tested version. Source: {url}")
        path.write_bytes(content)
        print(f"Downloaded {name}")

    archive = output.with_suffix(".zip")
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for name in SOURCES:
            bundle.write(output / name, name)
    print(archive)


if __name__ == "__main__":
    main()
