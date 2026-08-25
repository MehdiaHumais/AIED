import os, sys, json, asyncio
os.chdir(r"D:\sir projectss\Britsync AI Engineering Department (AIED)\ai-engineering")
sys.path.insert(0, ".")

from shared.config import config
from llms.manager import LLMManager

async def test():
    mgr = LLMManager(config.llm)
    await mgr.initialize()
    
    prompt = """Fix this error in app/page.tsx:

ERROR: Module '"@/auth"' declares 'authOptions' locally, but it is not exported.
Line 3: import { authOptions } from "@/auth";

The fix: change @/auth to @/auth/options

Current app/page.tsx:
```
import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/auth";

export default async function Home() {
  const session = await getServerSession(authOptions);
  if (!session) { redirect("/auth/signin"); }
  return <div>Hello</div>;
}
```

Output ONLY the fixed file:
app/page.tsx
```typescript
(full fixed content)
```
"""
    
    print("Calling backend-engineer agent (nvidia/nemotron-3-super-120b-a12b:free)...")
    try:
        result = await mgr.chat(
            messages=[{"role": "user", "content": prompt}],
            model="nvidia/nemotron-3-super-120b-a12b:free",
            temperature=0.3,
            max_tokens=4096,
        )
        print(f"\n=== RESPONSE ({len(result)} chars) ===")
        print(result[:2000])
        print("=== END ===")
        
        # Test file extraction
        from pipeline.engine import Pipeline
        p = Pipeline.__new__(Pipeline)
        files = p._extract_files_from_response(result)
        print(f"\n=== EXTRACTED {len(files)} files ===")
        for f in files:
            print(f"  {f['filename']} ({len(f['content'])} chars)")
            print(f"  Content: {f['content'][:200]}")
            
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(test())
