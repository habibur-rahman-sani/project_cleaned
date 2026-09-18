# এই ফোল্ডার এখন খালি — এটা ঠিকই আছে

আগে এখানে `DEPLOY_BANGLA.md` নামে একটা আলাদা গাইড ছিল, কিন্তু
`TEST_AND_DEPLOY_BANGLA.md` (রিপো রুটে) সব deploy তথ্য (local + Railway + VPS)
এক জায়গায় নিয়ে গেছে বলে ওটা মুছে ফেলার তালিকায় ছিল। প্রকৃত deploy করার জন্য
আসলে এই ফোল্ডারে কোনো ফাইলের দরকারই নাই:

- **Railway**: রুটের `railway.toml` অটো-ডিটেক্ট হয়, যেটা
  `hermes-multiuser-stack/gateway/Dockerfile` বিল্ড করে — এখানে আলাদা কিছু
  লাগে না।
- **VPS**: `setup/setup_all.sh production` ব্যবহার হয়।

গাইডের জন্য দেখো: `../TEST_AND_DEPLOY_BANGLA.md`
